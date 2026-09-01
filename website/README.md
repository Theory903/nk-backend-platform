# EVA Template documentation

This site publishes the curated documentation in `../docs/wiki/` using
[Docusaurus](https://docusaurus.io/). Internal plans and session notes are not
part of the site.

## Installation

```bash
npm ci
```

**Note**: feel free to use the package manager of your choice.

## Local Development

```bash
npm run start
```

This command starts a local development server. Most changes are reflected
live without restarting the server.

## Build

```bash
npm run build
```

This command generates static content into the `build` directory.

## Source and reliability

The source of truth is `../docs/wiki/`. Update the implementation, contracts,
and matching wiki page together. Run `npm run build` before opening a change;
the build fails on broken links and broken Markdown images when referenced.
