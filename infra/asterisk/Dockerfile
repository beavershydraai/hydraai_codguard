# Asterisk 20 from Alpine's own packages. Run it with docker-compose.yml (host networking).
FROM alpine:3.22
RUN apk add --no-cache asterisk asterisk-sample-config asterisk-sounds-en asterisk-sounds-moh \
        asterisk-srtp asterisk-opus sox \
    && sed -i -e 's/^rtpstart=.*/rtpstart=10000/' -e 's/^rtpend=.*/rtpend=10100/' /etc/asterisk/rtp.conf \
    && mkdir -p /var/run/asterisk \
    && chown -R asterisk:asterisk /var/run/asterisk /var/lib/asterisk /var/spool/asterisk /var/log/asterisk
# RTP only on 10000-10100, so the VM's firewall rule for media can stay narrow.
# sox converts audio prompts (dev-setup.sh uses it when the VM has none).
CMD ["asterisk", "-f", "-U", "asterisk", "-G", "asterisk"]
