// jsdom has <dialog> but not its modal methods. These stand in with what the tests rely on: the
// open attribute, and the close event the browser fires. A test run in Node has no DOM at all.
if (
  typeof HTMLDialogElement !== "undefined" &&
  typeof HTMLDialogElement.prototype.showModal !== "function"
) {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    if (!this.open) return;
    this.open = false;
    this.dispatchEvent(new Event("close"));
  };
}

// jsdom does no layout, so it has no ResizeObserver; the chat's viewport observes its size to keep
// the newest message in view. Nothing under test depends on a size.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Nor does it scroll; the viewport scrolls to the newest message.
if (typeof Element !== "undefined") Element.prototype.scrollTo ??= () => {};
