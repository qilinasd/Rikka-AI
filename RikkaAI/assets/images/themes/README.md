# Seasonal backgrounds

RikkaAI looks for one optional, character-free image per season:

- `spring/background.png`
- `summer/background.png`
- `autumn/background.png`
- `winter/background.png`

Use a 16:9 image, preferably 3840x2160. The application scales it with a
cover crop. If a file is missing or cannot be decoded, the theme manager uses
the built-in 1920x1080 procedural background instead.

Keep character artwork separate from these files so the character can be
replaced without rebuilding the seasonal themes.

Each season also includes `buttons.png`, a 2880x2880 production reference
sheet for the runtime button language: primary/secondary/compact buttons,
icon buttons, chips, toggles, sliders, and their interaction states. The
application uses the same seasonal palette and state rules from the theme
override stylesheet for live controls; the sheet is kept alongside the theme
artwork for export and future slicing.
