"""Build-time content pipeline.

Fetches guideline content and resources from pedsconcussion.com, pairs English resources
with their French equivalents, and renders the artefacts the app consumes
(`lib/i18n/resourceLinks.ts`, `all_rec_markdown.md`, `data/content-manifest.json`).

This runs in CI, never at request time. See CONTENT_PIPELINE_PLAN.md.
"""
