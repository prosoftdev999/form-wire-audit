FROM python:3.13-slim-bookworm
WORKDIR /app

# Keep the capture evidence outside the writable work area.  The agent can read
# the capture through /app/data, but cannot rewrite the evidence, the verifier
# log location, or the interpreter installation while working on the task.
COPY data/ /evidence/
COPY collect_formdata.py /app/collect_formdata.py
RUN mkdir -p /home/agent /app/output /logs/verifier \
    && printf 'agent:x:1000:1000::/home/agent:/bin/sh\n' >> /etc/passwd \
    && printf 'agent:x:1000:\n' >> /etc/group \
    && chown -R 1000:1000 /home/agent /app/output \
    && chmod 0700 /home/agent \
    && find /evidence -type d -exec chmod 0555 {} + \
    && find /evidence -type f -exec chmod 0444 {} + \
    && ln -s /evidence /app/data \
    && chmod 0444 /app/collect_formdata.py \
    && chmod 0555 /logs/verifier \
    && chmod 1777 /app

USER 1000:1000
ENV HOME=/home/agent
CMD ["sleep", "infinity"]
