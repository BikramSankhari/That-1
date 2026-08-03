FROM rancher/k3s:latest

COPY private.key /keys/private.key
COPY public.pub /keys/public.pub
COPY entrypoint.sh /entrypoint.sh
COPY helm /helm
RUN chmod +x /entrypoint.sh

ENTRYPOINT []

CMD ["/entrypoint.sh"]
