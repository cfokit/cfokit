/**
 * Just enough XML for a spreadsheet's parts. A Web Worker has no `DOMParser`, and a spreadsheet
 * part is plain elements, attributes and text.
 *
 * **A document type declaration is refused.** Entity-expansion attacks — billion laughs, quadratic
 * blowup — need a `DOCTYPE` carrying `ENTITY` declarations, and a spreadsheet part never has one.
 * Refusing the declaration outright is a complete defense against that class, and this parser
 * expands no entity but XML's five and character references anyway.
 */

import { Refused } from "./refused";

export interface Element {
  /** The name without its namespace prefix. */
  name: string;
  /** Attributes by name without a prefix: `r:id` is `id`. */
  attributes: Record<string, string>;
  children: Element[];
  /** The text directly inside this element. */
  text: string;
}

const TOKEN =
  /<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<!\[CDATA\[([\s\S]*?)\]\]>|<(\/?)([^\s/>]+)([^>]*?)(\/?)>|([^<]+)/g;
const ATTRIBUTE = /([^\s=]+)\s*=\s*("([^"]*)"|'([^']*)')/g;

function local(name: string): string {
  const colon = name.lastIndexOf(":");
  return colon < 0 ? name : name.slice(colon + 1);
}

function unescape(text: string): string {
  return text.replace(/&(#x[0-9a-fA-F]+|#\d+|lt|gt|amp|quot|apos);/g, (_, entity: string) => {
    switch (entity) {
      case "lt":
        return "<";
      case "gt":
        return ">";
      case "amp":
        return "&";
      case "quot":
        return '"';
      case "apos":
        return "'";
    }
    const code = entity[1] === "x" ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10);
    return String.fromCodePoint(code);
  });
}

/** One part as a tree, refusing a document type declaration. */
export function parse(payload: Uint8Array): Element {
  const text = new TextDecoder().decode(payload);
  const head = text.slice(0, 4096).toUpperCase();
  if (head.includes("<!DOCTYPE") || head.includes("<!ENTITY")) {
    throw new Refused("unreadable_figure", "a spreadsheet part declares a document type");
  }

  const root: Element = { name: "", attributes: {}, children: [], text: "" };
  const open: Element[] = [root];
  for (const match of text.matchAll(TOKEN)) {
    const [, cdata, closing, tag, attributes, selfClosing, chars] = match;
    const current = open[open.length - 1] ?? root;
    if (chars !== undefined) {
      current.text += unescape(chars);
    } else if (cdata !== undefined) {
      current.text += cdata;
    } else if (tag !== undefined) {
      if (closing === "/") {
        if (open.length > 1) open.pop();
        continue;
      }
      const element: Element = { name: local(tag), attributes: {}, children: [], text: "" };
      for (const [, key, , doubled, single] of (attributes ?? "").matchAll(ATTRIBUTE)) {
        if (key !== undefined) element.attributes[local(key)] = unescape(doubled ?? single ?? "");
      }
      current.children.push(element);
      if (selfClosing !== "/") open.push(element);
    }
  }
  const document = root.children[0];
  if (document === undefined)
    throw new Refused("unreadable_archive", "a spreadsheet part is empty");
  return document;
}

/** This element and every element beneath it, in document order. */
export function* descendants(element: Element): Generator<Element> {
  yield element;
  for (const child of element.children) yield* descendants(child);
}

/** All the text in the elements named `name` at or beneath this one, joined. */
export function textOf(element: Element, name: string): string {
  let text = "";
  for (const node of descendants(element)) if (node.name === name) text += node.text;
  return text;
}
