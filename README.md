# DatMail

DatMail is the SMTP mailing-list forwarder for `@fredagscafeen.dk`.

The current `master` branch is a hybrid SMTP + HTTP + object-storage system:

- Postfix receives inbound mail and relays outbound mail.
- DatMail applies mailing-list policy, spam checks, header rewriting, and resend handling.
- Mailing-list membership and spam-filter rules come from a Django API.
- Raw inbound `.eml` files are archived to S3-compatible storage.
- Processed and dropped mail is reported back to the Django backend.

## Documentation

| Location | Purpose |
| --- | --- |
| [GitHub wiki](https://github.com/fredagscafeen/mail/wiki) | Published developer docs, architecture, message flows, and API reference |
| [Architecture](https://github.com/fredagscafeen/mail/wiki/Architecture) | Docs for architecture, flows, and code map |
| [Message Flows](https://github.com/fredagscafeen/mail/wiki/Message-Flows) | Docs for message flows |
| [API Reference](https://github.com/fredagscafeen/mail/wiki/API-Reference) | Docs for API reference |

Recommended reading order:

1. [Wiki Home](https://github.com/fredagscafeen/mail/wiki)
2. [Architecture](https://github.com/fredagscafeen/mail/wiki/Architecture)
3. [Message Flows](https://github.com/fredagscafeen/mail/wiki/Message-Flows)
4. [API Reference](https://github.com/fredagscafeen/mail/wiki/API-Reference)
5. [Code Map](https://github.com/fredagscafeen/mail/wiki/Code-Map)

### Update the wiki

The wiki is a separate Git repository:

```bash
git clone git@github.com:fredagscafeen/mail.wiki.git
cd mail.wiki
git pull --rebase origin master
```

After editing the wiki pages:

```bash
git add .
git commit -m "docs: update wiki"
git push origin master
```

If the push is rejected, rebase on the latest wiki changes and push again:

```bash
git pull --rebase origin master
git push origin master
```

## Running with Docker

```bash
cp datmail/config.local.py datmail/config.py
docker-compose up --build
```

DatMail listens on port `9000` and relays outbound mail to `host.docker.internal:25`.

The resend control endpoint listens on port `9001` inside the container by default.

Useful commands:

```bash
docker-compose up -d --build
docker-compose logs -f app
docker-compose down
```

## Running locally

Python `3.8.10` is the expected runtime version.

```bash
python3 -m venv ~/.cache/venvs/fredagscafeen-mail
source ~/.cache/venvs/fredagscafeen-mail/bin/activate
pip install pip-tools
pip-sync requirements.txt dev-requirements.txt
pre-commit install
```

Then start DatMail with:

```bash
python3 -m datmail
```

## Configuration

Create `datmail/config.py` from the checked-in sample:

```bash
cp datmail/config.local.py datmail/config.py
```

At minimum, configure:

- `SRS_SECRET`
- `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`
- `DATMAIL_CONTROL_HOST`, `DATMAIL_CONTROL_PORT`, `DATMAIL_CONTROL_TOKEN`
- the Django API base URL and token used by `datmail/django_api_client.py`

For the detailed API contracts and payload shapes, use the [GitHub wiki API Reference](https://github.com/fredagscafeen/mail/wiki/API-Reference).

## Monitoring

The legacy monitoring job is still used for local error digests:

```bash
python3 -m datmail.monitor
```

It reads `error/`, emails an admin digest when the threshold is reached, and archives handled reports into `errorarchive/`.
