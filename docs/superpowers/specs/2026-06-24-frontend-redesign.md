# HO.ME Frontend Redesign — Design Spec
_2026-06-24_

## Summary

Complete visual redesign of the postcode lookup frontend using the official HO.ME brand assets. Applies to both the Flask template (`templates/index.html`) and the static GitHub Pages version (`docs/index.html`).

## Brand Assets Used

All from `/Home Assets/`:
- `HO.ME Map.svg` — London map shape with HO.ME branding; used in header top-left. Colours adapted for dark background: beige fills (`#e7e0d8`) → white tint (`rgba(255,255,255,0.13)`), dark teal fills (`#2e5b5f`) → white.
- `HOspital near ME.svg` — full wordmark; used in header next to map. "ME" paths (`#2e5b5f`) changed to white for contrast on dark header.
- `Fredoka Variable Font.ttf` — brand font; used throughout via `@font-face`.

## Colour Palette

| Token | Hex | Usage |
|---|---|---|
| Teal | `#66bca2` | Accent elements, L2 pin, borders, tab underline tint |
| Dark teal | `#2e5b5f` | Header bg, footer bg, body text, L1 pin |
| Orange | `#d2712a` | CTA button, L3 pin, active tab indicator, distances |
| Off-white | `#f4f9f7` | Search area bg, page bg |
| White | `#ffffff` | Cards, search input |

## Layout

### Header
- Background: `#2e5b5f`
- Left: `HO.ME Map.svg` (inline SVG, height 64px, colour-adapted)
- Right: `HOspital near ME.svg` (inline SVG, height 48px, ME in white)
- Bottom: thin accent strip — gradient `#66bca2 → #d2712a → #66bca2`

### Search Area
- Background: `#f4f9f7`, padding 20px 28px
- Input: white, 2px border `#cce8e0`, rounded 10px, Fredoka 15px placeholder
- Button: `#d2712a`, white text, Fredoka 15px 600 weight, "Find hospitals"

### Tabs
- Background: `#f4f9f7`, bottom border `#e0eeeb`
- Active tab: `#2e5b5f` text, 3px bottom border `#d2712a`
- Inactive: `#999` text

### Result Cards
- White background, 1.5px border `#e0eeeb`, border-radius 10px
- L3 (closest any): orange border + orange bg tint, orange pin circle
- L2: teal (`#66bca2`) pin circle
- L1: dark teal (`#2e5b5f`) pin circle
- Distance: `#d2712a` right-aligned
- All text: Fredoka font

### Footer
- Background: `#2e5b5f`
- Text: `rgba(255,255,255,0.45)`, Fredoka 12px
- Links: HO.ME · ~326,000 London-area postcodes · Catchment Map · Extra Maps

## Files to Change

1. `templates/index.html` — Flask template; rebuild with new design, keep Jinja/API calls intact
2. `docs/index.html` — Static site; rebuild with new design, keep existing JS data-fetching logic intact
3. `docs/Fredoka Variable Font.ttf` — copy font asset so GitHub Pages can serve it
4. `docs/HO.ME Map.svg` — copy for GitHub Pages
5. `docs/HOspital near ME.svg` — copy for GitHub Pages

## Constraints

- The Flask app and static site have different data layers (API vs JSON fetch) — the HTML structure/CSS should be shared/identical, only the JS differs.
- Font must be embedded as `@font-face` using a relative path (both versions serve from their own directory).
- Existing functionality must be preserved: postcode lookup, map display, catchment tab, loading states, error states.
