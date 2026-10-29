---
description: Render a site, run the design detector and a phone-size screenshot, and fix problems
---

1. Read `PRODUCT.md` and `DESIGN.md`.
2. Render the site: `agency demo-site --theme <theme>` or `agency preview --lead-id <id>`. Note the slug it prints (the folder name under `output/`).
3. Run `agency qa-site --slug <slug>`. It runs the Impeccable detector (needs Node) and takes a phone screenshot with playwright-cli (needs `npm i -g @playwright/cli`).
4. View `output/_qa/<slug>/mobile.png`. Check: call button visible without scrolling, hours readable, nothing overflows horizontally, text contrast looks fine.
5. If Impeccable is installed, run `/impeccable audit` on the template files. Fix findings; do not add decoration to silence them.
6. Re-run steps 2-4 until the detector is clean and the screenshot looks right. Run `pytest -q`.
7. Report what changed, with the final detector line and the screenshot path.
