# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-19

### Added

- Instant Scaffolding — One command creates a fully typed skill skeleton with Pydantic models and metadata.
- Test Generator — Produces deterministic unit tests plus LLM-as-judge cases from a one-line description.
- Benchmark Runner — Runs skills against scenario packs and reports accuracy, latency and token metrics.
- Auto Documentation — Renders Markdown reference with examples, parameters and compatibility notes.
- Standard Interface — BaseSkill.execute(context) plus metadata ensures drop-in use with LangGraph or CrewAI.
- Compatibility Check — Validates against known agent runtimes and flags missing required fields.
- One-click Packaging — Bundles skill into importable module or JSON manifest for sharing.
- Local Registry — Catalog, search and install skills from disk without leaving the CLI.
