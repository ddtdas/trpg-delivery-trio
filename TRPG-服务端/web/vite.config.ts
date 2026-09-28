import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// TRPG v1 前端（M0 骨架）：构建产物进 web/dist，由 FastAPI 静态托管。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // 后端联调在后续 WS 任务；此处仅预留代理（远程 9210）。
      '/api': 'http://127.0.0.1:9210',
      '/ws': {
        target: 'ws://127.0.0.1:9210',
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // UI-3 (additive, 仅构建配置): 资产内联阈值 40KB -> 小图/svg 直接内联, 减少请求数。
    assetsInlineLimit: 40960,
    // manualChunks 分包: 入口只留应用代码, react 栈/konva/其余依赖拆为独立 chunk
    // (三端页面为同一 SPA 的组件路由, 无 React.lazy 动态导入——业务代码不改,
    //  故按依赖族分包而非按页面分包; 入口体积因此显著变小)。
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id: string): string | undefined {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('konva') || id.includes('react-konva')) return 'vendor-konva';
          // UI-3 曾将 react 与其余 misc 拆开导致跨 chunk 循环 import（顶层 useLayoutEffect undefined → 白屏）；
          // 修复：react 栈与其余依赖合入同一 vendor chunk（同 chunk 无跨 chunk 循环），konva 独立自包含。
          return 'vendor';
        },
      },
    },
  },
  // t22: 后端经 /app/* 托管 dist（/app 无尾斜杠 URL 下 ./ 会解析到 /），
  // 故 base 固定为绝对子路径 /app/。
  base: '/app/',
});
