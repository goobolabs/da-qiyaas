import sqlite3
from uuid import uuid4

import pytest
from flask import Flask
from backend.feedback import feedback_blueprint


@pytest.fixture
def setup(tmp_path):
    database = tmp_path / 'feedback.sqlite3'
    app = Flask(__name__)
    app.register_blueprint(feedback_blueprint(database))
    return app.test_client(), database


def payload(**changes):
    return dict(submission_id=str(uuid4()), estimated_age=32, actual_age=28, source='upload', consent=True, **{}) | changes


def test_feedback_persists_and_retry_does_not_duplicate(setup):
    client, database = setup
    body = payload()
    for _ in range(2):
        response = client.post('/api/feedback', json=body)
        assert response.status_code == 200
        assert response.json['absolute_error_years'] == 4
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT estimated_age, actual_age, source FROM feedback').fetchall() == [(32, 28, 'upload')]
    assert client.post('/api/feedback', json=body | {'actual_age': 29}).status_code == 409


@pytest.mark.parametrize('changes', [
    {'consent': False}, {'consent': 1}, {'actual_age': True}, {'actual_age': -1},
    {'actual_age': 121}, {'actual_age': 2.5}, {'estimated_age': '32'},
    {'source': 'other'}, {'submission_id': 'bad'}, {'image': 'not allowed'},
])
def test_invalid_feedback_is_not_saved(setup, changes):
    client, database = setup
    assert client.post('/api/feedback', json=payload(**changes)).status_code == 400
    assert not database.exists()


def test_storage_failure_is_recoverable(tmp_path):
    app = Flask(__name__)
    app.register_blueprint(feedback_blueprint(tmp_path))
    response = app.test_client().post('/api/feedback', json=payload())
    assert response.status_code == 503
    assert response.json['error']['code'] == 'FEEDBACK_UNAVAILABLE'


@pytest.mark.parametrize('age', [0, 120])
def test_boundary_ages(setup, age):
    client, _ = setup
    assert client.post('/api/feedback', json=payload(actual_age=age)).status_code == 200


def test_summary_empty_does_not_create_database(setup):
    client, database = setup
    response = client.get('/api/feedback/summary')
    assert response.status_code == 200
    assert response.json['count'] == 0
    assert response.json['mean_absolute_error_years'] is None
    assert response.json['by_source']['camera']['mean_absolute_error_years'] is None
    assert response.headers['Cache-Control'] == 'no-store'
    assert not database.exists()


def test_summary_weights_submissions_and_separates_sources(setup):
    client, _ = setup
    for body in [payload(estimated_age=40, actual_age=30, source='camera'),
                 payload(estimated_age=20, actual_age=20),
                 payload(estimated_age=28, actual_age=30)]:
        assert client.post('/api/feedback', json=body).status_code == 200
    result = client.get('/api/feedback/summary').json
    assert result == {'count': 3, 'mean_absolute_error_years': 4.0, 'self_reported': True,
                      'by_source': {'camera': {'count': 1, 'mean_absolute_error_years': 10.0},
                                    'upload': {'count': 2, 'mean_absolute_error_years': 1.0}}}


def test_summary_storage_error_is_not_empty_data(setup):
    client, database = setup
    database.write_text('invalid sqlite file')
    assert client.get('/api/feedback/summary').status_code == 503


def training_request(client, body, raw=None):
    import io
    import json
    from PIL import Image
    if raw is None:
        output = io.BytesIO()
        Image.new('RGB', (100, 100), 'green').save(output, format='PNG')
        raw = output.getvalue()
    return client.post('/api/feedback', data={'metadata': json.dumps(body), 'image': (io.BytesIO(raw), 'private-name.png')})


@pytest.fixture
def training_setup(tmp_path):
    from backend.app import decode_image, InputError
    app = Flask(__name__)
    database = tmp_path / 'feedback.sqlite3'
    app.register_blueprint(feedback_blueprint(database, decode_image))
    @app.errorhandler(InputError)
    def invalid(error):
        return {'error': error.code}, error.status
    return app.test_client(), database


def test_training_requires_separate_consent(training_setup):
    client, database = training_setup
    assert training_request(client, payload()).status_code == 400
    assert not database.exists()
    assert client.post('/api/feedback', json=payload(training_consent=True)).status_code == 400
    assert not database.exists()


def test_training_photo_is_atomic_and_idempotent(training_setup):
    import io
    from PIL import Image
    client, database = training_setup
    body = payload(training_consent=True)
    for _ in range(2):
        response = training_request(client, body)
        assert response.status_code == 200
        assert response.json['training_saved'] is True
    with sqlite3.connect(database) as connection:
        rows = connection.execute('SELECT image_jpeg, consent_version, review_status FROM training_contributions').fetchall()
        assert len(rows) == 1
        assert rows[0][1:] == ('training-photo-v1', 'pending')
        assert Image.open(io.BytesIO(rows[0][0])).format == 'JPEG'
        assert connection.execute('SELECT COUNT(*) FROM feedback').fetchone()[0] == 1
    assert client.post('/api/feedback', json=body | {'training_consent': False}).status_code == 409


def test_invalid_training_photo_is_not_saved(training_setup):
    client, database = training_setup
    assert training_request(client, payload(training_consent=True), b'not a photo').status_code == 400
    assert not database.exists()


def test_regular_feedback_does_not_save_photo(training_setup):
    client, database = training_setup
    assert client.post('/api/feedback', json=payload()).json['training_saved'] is False
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM training_contributions').fetchone()[0] == 0
