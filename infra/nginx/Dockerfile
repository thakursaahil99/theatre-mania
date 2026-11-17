FROM nginx:1.27-alpine
# Drop the stock vhost (it claims server_name localhost and would shadow ours).
RUN rm -f /etc/nginx/conf.d/default.conf
# Rendered into /etc/nginx/conf.d/ by the image's envsubst entrypoint at container start.
COPY templates/ /etc/nginx/templates/
