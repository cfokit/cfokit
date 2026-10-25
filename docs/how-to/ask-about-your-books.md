# Ask CFOKit about your books

Once your books are in, you can ask about them in CFOKit itself: open your company and type a
question. CFOKit answers from your books, through the same tools Claude uses, and shows which ones
it read. Your own Claude works too, and [Connect Claude](connect-claude.md) explains how.

The chat needs the deployment to run CFOKit's agent with an inference credential. On a CFOKit you
run, set `ANTHROPIC_API_KEY` for the `agent` service in `compose.yaml`. Without one, the chat
says it is off.

The clips below are recorded by CI from a passing run against the compose stack. The answers in
them come from a scripted stand-in for the model, because CI holds no credential. The tool it
calls and every figure it shows are real: they are the sample export's own books.

## 1. Ask CFOKit here

At the end of getting started, choose **Ask CFOKit here instead**. Later, your company opens on
its chat. The first question is waiting in the box, unsent.

The first time, CFOKit asks to be allowed in your company. It acts for you, as an agent, and you
decide what it may do.

[![The chat, with the first question waiting, asking to be allowed](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/ask-about-the-books-01-ask-cfokit-here.png)](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/ask-about-the-books-01-ask-cfokit-here.mp4)

## 2. Allow CFOKit in your company

Choose **Allow CFOKit**, then **Allow to keep the books**, or **Allow to read only** if it should
only read. Then choose **Ask CFOKit**: you are back in the chat, with your question as you left it.

[![Allowing CFOKit, and back in the chat](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/ask-about-the-books-02-allow-cfokit-in-your-company.png)](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/ask-about-the-books-02-allow-cfokit-in-your-company.mp4)

## 3. Read the answer

Choose **Send**. Each tool CFOKit reads shows as a line, such as **Read profit and loss**, and the
answer follows, with its figures from your books. While it answers, **Stop** ends the answer.

[![The answer: the profit and loss, from the books](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/ask-about-the-books-03-read-the-answer.png)](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/ask-about-the-books-03-read-the-answer.mp4)

## 4. Come back to it

Everything said is kept. Reload, or come back another day, and the conversation is as you left
it.

[![The same conversation after a reload](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/ask-about-the-books-04-come-back-to-it.png)](https://github.com/cfokit/cfokit/releases/download/onboarding-recording/ask-about-the-books-04-come-back-to-it.mp4)

## When something is in the way

- **Not allowed yet.** Choose **Allow CFOKit**, as in step 2. Someone who administers the company
  has to allow it.
- **Chat is off.** The deployment has no inference credential. Ask your own Claude instead, or
  set `ANTHROPIC_API_KEY`.
- **No chat here.** The deployment does not run CFOKit's agent. Connect your own Claude from
  **Settings**.
