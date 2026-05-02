# Dark Mode Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make the service UI automatically use a dark theme when the user's system prefers dark mode, without adding a manual theme switch.

**Architecture:** Keep the existing single-file UI structure in `index.html` and extend the current CSS token system. Define dark theme variables with `@media (prefers-color-scheme: dark)` so the browser handles theme selection automatically and no JavaScript state is needed.

**Tech Stack:** Static HTML, inline CSS, inline JavaScript, browser-native `prefers-color-scheme`

---

### Task 1: Add dark theme design tokens

**Objective:** Introduce a dark token set that overrides the current light palette based on system settings.

**Files:**
- Modify: `index.html`

**Step 1: Update root color scheme support**

Change the existing `:root` block so `color-scheme` advertises both themes instead of only light.

Expected direction:
```css
:root {
  color-scheme: light dark;
  /* existing light theme tokens stay here */
}
```

**Step 2: Add a dark-mode media query**

Add an `@media (prefers-color-scheme: dark)` block after the base token definitions and override only the variables needed for dark mode.

Include tokens for:
- page background and accent background
- glass/surface layers
- body text and muted text
- border lines and stronger borders
- brand button colors
- shadow intensity

Expected direction:
```css
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1412;
    --bg-accent: #16201b;
    --surface: rgba(18, 24, 21, 0.84);
    --surface-strong: rgba(24, 31, 27, 0.94);
    --text: #edf3ee;
    --muted: #a6b5ab;
    --line: rgba(237, 243, 238, 0.1);
    --line-strong: rgba(237, 243, 238, 0.18);
    --brand: #5db587;
    --brand-strong: #79c79a;
    --shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
  }
}
```

**Step 3: Verify token coverage**

Check that the existing components already consume variables for backgrounds, text, borders, and CTA styling so the dark theme propagates without structural markup changes.

Run: `rg -n "var\(--|color-scheme|prefers-color-scheme" ~/projects/docker-service-dashboard/index.html`
Expected: CSS variables are used by `html`, `.hero`, `.card`, `.link`, `.empty`, `.error`, and text styles.

### Task 2: Patch component-specific contrast gaps

**Objective:** Fix any elements that still rely on hard-coded light colors and would look wrong in dark mode.

**Files:**
- Modify: `index.html`

**Step 1: Review hard-coded color values**

Inspect the stylesheet for literal colors that bypass theme variables.

Run: `rg -n "#|rgba\(" ~/projects/docker-service-dashboard/index.html`
Expected: Most values are token definitions; any component-level hard-coded color should be reviewed.

**Step 2: Replace theme-sensitive literals with variables if needed**

Likely candidates:
- pill backgrounds like `.eyebrow`, `.stat`, `.port`
- button text color if pure white looks too bright against the dark brand tone
- error border styling if it lacks enough separation on dark backgrounds

Preferred approach:
- keep current visuals if contrast is good
- otherwise add new tokens such as `--pill-bg`, `--port-bg`, `--button-text`, `--error-line`
- override those tokens inside the dark media query instead of branching component rules

**Step 3: Sanity-check hover and focus states**

Confirm the CTA remains readable and the hover shadow is still visible in dark mode.

### Task 3: Verify behavior in both themes

**Objective:** Make sure the UI looks correct in light and dark system modes and still works for live and file preview data.

**Files:**
- Verify: `index.html`

**Step 1: Run the service locally**

Run from the repo root:
```bash
python3 app.py
```

Expected: the local server starts and serves the dashboard.

**Step 2: Check light and dark rendering in a browser**

Verify:
- system light mode keeps the current look
- system dark mode switches automatically with no toggle
- cards, hero panel, stats pills, port badge, and button remain readable
- page background gradient still feels intentional instead of muddy

**Step 3: Check file preview fallback**

Open `index.html` directly in the browser and confirm the demo content also renders correctly in both system themes.

**Step 4: Optional screenshot diff**

Capture one screenshot in light mode and one in dark mode for a quick visual regression check before merging.

## Notes

- Keep this feature CSS-only. JavaScript does not need theme detection.
- Do not add local storage, toggle UI, or query-parameter theme overrides.
- Prefer token overrides over duplicating full component rules.
- Since this repo has no front-end test harness, verification is visual/manual.
