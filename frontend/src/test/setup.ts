import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// With `globals: false`, RTL cannot auto-register cleanup — do it explicitly.
afterEach(() => {
  cleanup();
});

// jsdom does not implement `scrollIntoView`; the chat auto-scroll relies on it.
if (typeof Element !== 'undefined' && typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = () => undefined;
}
