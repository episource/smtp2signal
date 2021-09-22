#!/bin/sh

set -x
set -e

# ensure correct permissions on bind mounts
chown ${SIGNAL_SMTP_USER}:${SIGNAL_SMTP_USER} -R /home

# Show warning on docker exec
cat <<EOF >> /root/.bashrc
echo "NOTE: smtp2signal runs as user ${SIGNAL_SMTP_USER}. You are root." 
EOF

su-exec ${SIGNAL_SMTP_USER} /usr/local/bin/smtp2signal.py
