/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 백엔드 API 루트 (예: https://api.example.com). 끝의 `/`는 무시됩니다. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
