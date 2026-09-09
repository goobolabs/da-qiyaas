# Spoken age estimates

Speak only the completed, rounded estimate for camera and upload results:
“Da’daada waxaa lagu qiyaasay 24 sano.” Never announce intermediate samples.

- Sound defaults off. Persist the user's choice in localStorage.
- Offer replay after a result and cancel playback on mute, retry, mode change or unmount.
- Prefer an available Somali browser voice. Never substitute an unrelated language.
- Support Azure's so-SO-UbaxNeural voice when server credentials are configured.
- Send only an integer age (0–120) to the speech endpoint; generate a fixed sentence server-side.
- Keep credentials server-side. Bound network time and cache the 121 possible clips in memory.
- Speech failures must leave the visual prediction usable and explain how to replay.
- Verify completed-result playback, cancellation, unsupported voices, failures, persistence and endpoint validation.
- Live Azure pronunciation needs credentials and a listening check; mocked tests cannot verify voice quality.
