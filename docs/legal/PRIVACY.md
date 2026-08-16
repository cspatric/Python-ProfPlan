# Privacy

Written to be read by the teacher whose material this is, not by a lawyer.
Where the law is involved it is Brazil's LGPD, and the two obligations that
shaped the code are the right to take your data with you and the right to have
it deleted.

## What is stored

| | |
| --- | --- |
| **Account** | name, email, password hash (Argon2id), and, if you signed in with Google, the identifier Google gives us for you |
| **Your material** | the files you upload, the text extracted from them, and the passages indexed for search |
| **Your work** | subjects, plans, modules, activities, and the passages each activity was written from |
| **Security log** | sign-ins, failures, password resets, with IP address and user agent |
| **AI usage** | tokens and cost per generation run |

The security log exists because "somebody signed in from this address four
hundred times" is the record an intrusion is found in. It is kept for that and
nothing else.

## Where it goes

Passages of your uploaded material are sent to a language model to write the
activities. That is the product. Which model depends on the configuration of
the deployment, and in this one it can be:

| processor | what it receives | where |
| --- | --- | --- |
| Amazon Bedrock (Anthropic, Amazon models) | the prompt: passages of your documents and your plan's parameters | us-east-1 |
| Google (Gemini API) | the same, when the chain falls through to it | Google's infrastructure |
| OpenAI | the same, when the chain falls through to it | OpenAI's infrastructure |
| Resend | your email address and the message, for password resets | Resend's infrastructure |

Nothing else leaves. The prompt is never written to the logs: the per-call
record keeps the provider, the model, the token counts, the cost and the
latency, and not the text.

A self-hosted deployment can run the whole chain on a local model (Ollama) and
send nothing anywhere, which is the reason the local model is in the fallback
chain at all.

## What you can do about it

| right | how |
| --- | --- |
| **Take it with you** | `GET /api/v1/users/me/export` returns one JSON file with the account, every subject, plan, module and activity, the text parsed from every document, and the passages behind each activity |
| **Delete it** | `POST /api/v1/users/me/delete` deletes the account and everything it owns, including the uploaded files in object storage |
| **Correct it** | the application itself: everything is editable by its owner |

Deletion is deletion. Not a flag on a row that still holds your material: the
rows go, the files go, and the security log keeps its events with your identity
overwritten, because a log the account it incriminates can empty is not a log,
and one that keeps names forever is not erasure.

The uploaded files themselves are not inlined in the export. They are the
originals you already have, a single plan can carry a hundred megabytes of PDF,
and an export nobody can open is not an export. What the export does carry is
the part this product made and nobody else has: the parsed text, the plans, the
activities and their sources.

## How long

While the account exists. There is no separate retention period, no analytics
profile and no third-party tracking of any kind: the application sets three
cookies, and all three are the session.

## Sub-processors change

The chain above is configuration, so a deployment can add or remove a provider.
If this becomes a service other people use, changing that list is a change to
this page, and a change to this page is something the people using it are told
about before it takes effect.
