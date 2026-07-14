# React + TypeScript + Vite

This is the Agent Inspector frontend: a minimal React + TypeScript app
built with Vite.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Linting and formatting

Linting is handled by [ESLint](https://eslint.org/) (flat config, see
`eslint.config.js`) and formatting by [Prettier](https://prettier.io/)
(see `.prettierrc.json`):

```bash
npm run lint          # eslint .
npm run format        # prettier --write .
npm run format:check  # prettier --check .
```

Both are also wired into the repo-root `.pre-commit-config.yaml`, so
`pre-commit run --all-files` from the repo root covers the frontend
too.
