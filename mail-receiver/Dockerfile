FROM alpine:3.19

RUN apk add --no-cache postfix

# UID 1000 owns the Maildir volume; shared with the digestor container
RUN adduser -D -u 1000 -h /data -s /bin/false mailuser

COPY main.cf /etc/postfix/main.cf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 25

ENTRYPOINT ["/entrypoint.sh"]
