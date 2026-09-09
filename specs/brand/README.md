# Goobo Labs visual reference

Source visited: https://www.goobolabs.so/en on 2026-09-09, using headless Edge after direct HTTP fetches failed.

Observed styles from computed browser CSS:

- Primary mint: #3ACC69; ink: #0C0C0C; page: #FAFAFA.
- Green heading accent on the source: #1F9A48.
- Headings: Space Grotesk, bold; body and controls: Manrope.
- Pill-shaped calls to action, white cards with neutral borders, generous rounded corners, subtle dotted backgrounds.
- Official logo: https://www.goobolabs.so/logo.svg.

Implementation uses these visual elements for Da’qiyaas. Content and navigation are specific to the age-estimation app; the source site's research statistics, authentication, and programs are not part of this application.

Local assets are in frontend/public/brand. Their original font URLs are recorded in assets.json; fonts are served locally and use the source's Latin glyph subset for the English interface. Reference computed styles are in reference.json. The copied SVG is used as an image, not injected markup.

Age estimation logic, camera scanning, quality checks, and uploaded-image inference are unchanged by this visual update.
