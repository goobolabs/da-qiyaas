"""Self-reported feedback with separate opt-in training contributions."""
import io
import json
import hashlib
import sqlite3
from pathlib import Path
from uuid import UUID

from flask import Blueprint, jsonify, request


def feedback_blueprint(database, decode_image=None):
    blueprint = Blueprint('feedback', __name__)
    database = Path(database)

    @blueprint.get('/api/feedback/summary')
    def summary():
        groups = {source: {'count': 0, 'mean_absolute_error_years': None} for source in ('camera', 'upload')}
        try:
            if database.exists():
                # Read-only access keeps an empty dashboard from creating a database.
                with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as connection:
                    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='feedback'").fetchone()
                    if exists:
                        for source, count, error in connection.execute('SELECT source, COUNT(*), AVG(ABS(estimated_age - actual_age)) FROM feedback GROUP BY source'):
                            if source in groups:
                                groups[source] = {'count': count, 'mean_absolute_error_years': error}
        except (OSError, sqlite3.Error):
            return jsonify(error={'code': 'FEEDBACK_UNAVAILABLE', 'message': 'Feedback summary is unavailable. Please try again.'}), 503
        count = sum(group['count'] for group in groups.values())
        mean = sum(group['count'] * (group['mean_absolute_error_years'] or 0) for group in groups.values()) / count if count else None
        response = jsonify(count=count, mean_absolute_error_years=mean, by_source=groups, self_reported=True)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @blueprint.post('/api/feedback')
    def submit():
        def invalid(message):
            return jsonify(error={'code': 'INVALID_FEEDBACK', 'message': message}), 400

        multipart = request.mimetype == 'multipart/form-data'
        if request.content_length and request.content_length > (8 * 1024 * 1024 + 65536 if multipart else 2048):
            return invalid('Feedback is too large.')
        if multipart:
            try:
                data = json.loads(request.form.get('metadata', ''))
            except ValueError:
                return invalid('Invalid feedback metadata.')
        else:
            data = request.get_json(silent=True)
        required = {'submission_id', 'estimated_age', 'actual_age', 'source', 'consent'}
        if not isinstance(data, dict) or not required <= set(data) or set(data) - required - {'training_consent'}:
            return invalid('Provide the ages, input method and consent.')
        training = data.get('training_consent', False)
        if type(training) is not bool:
            return invalid('Training consent must be explicitly selected.')
        if multipart and (set(request.files) != {'image'} or set(request.form) != {'metadata'} or not training):
            return invalid('A photo requires separate training consent.')
        if training and not multipart:
            return invalid('Attach the photo when contributing to training.')
        if data['consent'] is not True:
            return invalid('Choose to share your ages before submitting.')
        for field in ('estimated_age', 'actual_age'):
            if type(data[field]) is not int or not 0 <= data[field] <= 120:
                return invalid('Enter whole-number ages between 0 and 120.')
        if data['source'] not in ('camera', 'upload'):
            return invalid('Choose a valid input method.')
        try:
            submission_id = str(UUID(data['submission_id']))
        except (ValueError, TypeError, AttributeError):
            return invalid('Invalid submission identifier.')
        photo = None
        digest = None
        if training:
            raw = request.files['image'].read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                return invalid('Choose a photo under 8 MB.')
            if decode_image is None:
                return invalid('Training contributions are unavailable.')
            # Re-encode pixels to strip EXIF, filenames and other image metadata.
            portrait = decode_image(raw)
            portrait.thumbnail((1280, 1280))
            encoded = io.BytesIO()
            portrait.save(encoded, format='JPEG', quality=95)
            photo = encoded.getvalue()
            digest = hashlib.sha256(photo).hexdigest()
        try:
            database.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(database, timeout=5) as connection:
                connection.execute('''CREATE TABLE IF NOT EXISTS feedback (
                    submission_id TEXT PRIMARY KEY,
                    estimated_age INTEGER NOT NULL,
                    actual_age INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )''')
                connection.execute('''CREATE TABLE IF NOT EXISTS training_contributions (
                    submission_id TEXT PRIMARY KEY REFERENCES feedback(submission_id),
                    image_jpeg BLOB NOT NULL,
                    image_sha256 TEXT NOT NULL,
                    consent_version TEXT NOT NULL,
                    consented_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    review_status TEXT NOT NULL DEFAULT 'pending'
                )''')
                connection.execute('BEGIN IMMEDIATE')
                values = (data['estimated_age'], data['actual_age'], data['source'])
                previous = connection.execute(
                    'SELECT estimated_age, actual_age, source FROM feedback WHERE submission_id = ?',
                    (submission_id,),
                ).fetchone()
                prior_photo = connection.execute('SELECT image_sha256 FROM training_contributions WHERE submission_id = ?', (submission_id,)).fetchone()
                if previous and (previous != values or bool(prior_photo) != training or (prior_photo and prior_photo[0] != digest)):
                    return jsonify(error={'code': 'FEEDBACK_CONFLICT', 'message': 'Feedback was already submitted for this result.'}), 409
                connection.execute('INSERT OR IGNORE INTO feedback (submission_id, estimated_age, actual_age, source) VALUES (?, ?, ?, ?)', (submission_id, *values))
                if training:
                    connection.execute('INSERT OR IGNORE INTO training_contributions (submission_id, image_jpeg, image_sha256, consent_version) VALUES (?, ?, ?, ?)', (submission_id, photo, digest, 'training-photo-v1'))
        except (OSError, sqlite3.Error):
            return jsonify(error={'code': 'FEEDBACK_UNAVAILABLE', 'message': 'Feedback could not be saved. Please try again.'}), 503
        return jsonify(status='saved', absolute_error_years=abs(data['estimated_age'] - data['actual_age']), training_saved=training), 200

    return blueprint
