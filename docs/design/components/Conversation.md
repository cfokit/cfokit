# Conversation

A conversation with CFOKit's agent: the person's messages on the right in a `sunken` panel, the
agent's answers on the left as plain text, each tool the agent used as one `caption` line in
`ink-muted` ("Read profit and loss"), and a composer below with **Send**, or **Stop** while the
agent answers.

The agent writes Markdown. It renders as elements, with tables for figures, and never as HTML: a
`<script>` in an answer is shown as text, not run. Answers are prose, so their figures are the
model's text, not amounts the client formats; amounts the client shows itself still go through
`Money` and `MoneyTable`.

Give it `runtime`, an assistant-ui runtime such as the AG-UI one, for a live conversation. Give it
`messages` instead to show one read-only, with no composer, as the gallery and this guide's
preview do. `placeholder` is what the composer asks for and its accessible name: "Ask about your
books".

The component fills the height it is given and scrolls its messages, so place it in a container
with a height, such as the rest of a page below its heading.

Props: `runtime`, `messages`, `placeholder`.

```html
<x-import
  component-from-global-scope="CFOKit.Conversation"
  placeholder="Ask about your books"
></x-import>
```
