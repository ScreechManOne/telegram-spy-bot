# Security

## Secrets

- Never commit `.env`, `env.tx`, `database.db`, or any file containing `BOT_TOKEN`.
- Copy only `.env.example` to `.env` locally and fill in real values.
- If a token leaks, revoke it immediately in [@BotFather](https://t.me/BotFather) and issue a new one.

## Archive group

- `ARCHIVE_CHAT_ID` should point to a **private** supergroup where only you (and trusted admins) have access.
- The bot stores copies of incoming media there for delete notifications. Users of the bot do not see this group in the UI.
- With multiple connected Premium users, one shared archive group is used; service captions include `owner_id` for routing.

## Responsible use

- Use this bot only on accounts and chats you are allowed to monitor.
- Do not use it to spy on people without their knowledge where local law prohibits it.

## Before going public

If you fork or publish this repository, scan git history for accidental secrets:

```bash
git log -p --all -S "BOT_TOKEN"
git log -p --all -S "AA"
```

Replace leaked tokens even if the commit was reverted.
