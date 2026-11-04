import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Without vitest globals, Testing Library does not unmount after each test by itself.
afterEach(cleanup);

// jsdom has no layout engine. React Flow measures its nodes before it draws edges, so give
// every element a size and provide the two browser APIs it uses (as in the React Flow docs).
class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserver;
class DOMMatrixReadOnly {
  m22 = 1;
  constructor(transform?: string) {
    const scale = transform?.match(/scale\(([0-9.]+)\)/)?.[1];
    this.m22 = scale ? Number(scale) : 1;
  }
}
// @ts-expect-error: a minimal stand-in, not the full DOMMatrixReadOnly interface
globalThis.DOMMatrixReadOnly = DOMMatrixReadOnly;
Object.defineProperties(globalThis.HTMLElement.prototype, {
  offsetHeight: { get: () => 40 },
  offsetWidth: { get: () => 150 },
});
// Edge labels measure their SVG text.
// @ts-expect-error: jsdom has no SVG layout, so getBBox does not exist on SVGElement
globalThis.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 80, height: 16 });

// Node 25+ has its own Web Storage, which hides jsdom's: without --localstorage-file the
// global localStorage is undefined. Point it back at jsdom's, as a browser has it (#99).
// @ts-expect-error: vitest's jsdom environment puts the JSDOM instance on globalThis
Object.defineProperty(globalThis, "localStorage", { value: globalThis.jsdom.window.localStorage });
