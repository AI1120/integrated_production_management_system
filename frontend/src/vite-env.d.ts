/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute API base for builds served from a different origin than the API. */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
