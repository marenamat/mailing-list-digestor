# Mailing-list Digestor

The tool will directly receive various mailing-lists.
It should automatically process the mailbox and notify about important events.

## General rules

Commit everything into Git.

Document everything, both for developers and for users, most notably deployment needs.

Create automatic tests for every feature if possible.

Everything shall be logged.

## Mail receiver

There shall be a mailserver configured to receive e-mails for one single
address and never send anything. This address will be subscribed to various
public mailing-lists and is expected to read and process all that data.

This service must run separated from others and communicate only one-way with the digestor.

## Digestor

There shall be a service monitoring new e-mail delivery. This service shall
have access to the internet only for HTTP(S)-based requests and nothing else.

There shall be a triage phase running a small local model via ollama first.
This phase classifies the incoming messages whether they are urgent or not.
This model shall be biased a little towards urgency.

For urgent messages, a claude-LLM-based classifier shall run, deciding whether
that mail is indeed urgent, and if so, notify about them immediately.

For all other messages, once daily, a claude-LLM-based classifier shall run,
creating a digest.

Monitor the LLM token usage and append the usage report to the digest.

There shall be some database keeping the e-mails, digests and reports. It may
be a folder structure, as it will mostly be write once and not return back too often.

There shall be a full-text index of the e-mails, digests and reports, to allow
for faster searching.

If an e-mail is a reply (In-Reply-To, References) and the referenced mail is not available locally,
it shall be downloaded from public archives and considered received.

Split the digests by working groups. If the digestor finds out that nothing happened in some list,
it should be mentioned as "nothing here". If the digestor finds out that there is another mailing-list
worth being interested in, it shall recommend to subscribe there.

### Specific message types

Calls for presentations are always urgent. Also, setup a repeated notification:
- for IETF and everything else with deadline shorter than 2 weeks, every day until manually cancelled
- otherwise, once a week until manually cancelled

Messages about IETF interim meetings are always regular, but they also shall set several notifications:
- one week ahead
- that day morning
- half an hour ahead

Documents in last call are never irrelevant.

IETF Documents in working group adoption call are never irrelevant.

Confirmations of mailing-list subscriptions are always urgent.

### Digestor context

There shall be a context in which the messages are evaluated, to determine their relevance,
as a markdown file somewhere in the configuration.

## Notifier

The notifier is a Matrix user. The server, username and password shall be
configured. There shall be a configured whitelist of users allowed to communicate with the bot.
Every attempt to communicate from a non-whitelisted account shall be logged.

The whitelisted user gets digests and notifications.

The whitelisted user may reply to the messages from the bot. These should be processed and 
the digestor context updated accordingly. The changes shall be presented back in a concise form.

This service must run separated from others and communicate with the digestor only in a form of
a single messaging channel.
