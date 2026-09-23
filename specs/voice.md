# Spoken age estimates

Speak only the completed, rounded estimate for camera and upload results:
“Da’daada waxaa lagu qiyaasay 24 sano.” Never announce intermediate samples.

- Sound defaults off. Persist the user's choice in localStorage.
- Offer replay after a result and cancel playback on mute, retry, mode change or unmount.
- Prefer an available Somali browser voice. Never substitute an unrelated language.
- Serve pre-generated Somali clips from disk first, so speech needs no account, key or outbound request.
- Generate one clip per whole age from 0 to 120 with a reproducible script, and keep them out of Git.
- Reject any generated file that is not MP3 audio, so an error page is never saved as a clip.
- Keep Azure's so-SO-UbaxNeural voice as an optional fallback when clips are absent and credentials exist.
- Send only an integer age (0–120) to the speech endpoint; generate a fixed sentence server-side.
- Keep credentials server-side. Bound network time and cache the 121 possible clips in memory.
- Speech failures must leave the visual prediction usable and explain how to replay.
- Verify completed-result playback, cancellation, unsupported voices, failures, persistence and endpoint validation.
- Live Azure pronunciation needs credentials and a listening check; mocked tests cannot verify voice quality.
