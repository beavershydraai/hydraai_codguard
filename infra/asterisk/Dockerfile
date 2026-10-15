# Asterisk 20 from Alpine's own packages. Run it with docker-compose.yml (host networking).
FROM alpine:3.22
RUN apk add --no-cache asterisk asterisk-sample-config asterisk-sounds-en asterisk-sounds-moh \
        asterisk-srtp asterisk-opus sox \
    && sed -i -e 's/^rtpstart=.*/rtpstart=10000/' -e 's/^rtpend=.*/rtpend=10100/' /etc/asterisk/rtp.conf \
    && sed -i -e 's/^\[directories\](!)/[directories]/' \
        -e 's|^astdatadir => .*|astdatadir => /usr/share/asterisk|' \
        -e 's|^astagidir => .*|astagidir => /usr/share/asterisk/agi-bin|' /etc/asterisk/asterisk.conf \
    && mkdir -p /var/run/asterisk /var/cache/asterisk \
    && chown -R asterisk:asterisk /var/run/asterisk /var/cache/asterisk /var/lib/asterisk /var/spool/asterisk /var/log/asterisk
# Alpine installs sounds, music on hold and AGI under /usr/share/asterisk, but the sample
# asterisk.conf leaves the data directory at /var/lib/asterisk, where no prompt is found.
# RTP only on 10000-10100, so the VM's firewall rule for media can stay narrow.
# sox converts audio prompts (dev-setup.sh uses it when the VM has none).
CMD ["asterisk", "-f", "-U", "asterisk", "-G", "asterisk"]
