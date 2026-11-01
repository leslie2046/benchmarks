#!/bin/sh
set -eu

admin_username=${ADMIN_USERNAME-admin}
admin_password=${ADMIN_PASSWORD-}
auth_config=/etc/nginx/admin-auth.conf
password_file=/etc/nginx/admin.htpasswd
legacy_password_file=/etc/nginx/htpasswd

fail() {
    printf '%s\n' "$1" >&2
    exit 1
}

case "${AUTH_MODE-basic}" in
    app)
        printf 'auth_basic off;\n' > "$auth_config"
        exit 0
        ;;
    basic) ;;
    *) fail 'AUTH_MODE must be basic or app.' ;;
esac

if [ -n "$admin_password" ]; then
    case "$admin_username" in
        ''|*[!a-zA-Z0-9_.@-]*) fail 'ADMIN_USERNAME must contain only letters, digits, _, ., @ or -.' ;;
    esac
    if [ "$(printf '%s' "$admin_password" | tr -d '\r\n')" != "$admin_password" ]; then
        fail 'ADMIN_PASSWORD must not contain line breaks.'
    fi
    if [ "$(printf '%s' "$admin_password" | wc -c)" -gt 72 ]; then
        fail 'ADMIN_PASSWORD must not exceed 72 bytes (bcrypt limit).'
    fi
    umask 027
    printf '%s\n' "$admin_password" | htpasswd -niB -C 10 "$admin_username" > "$password_file"
    chown root:nginx "$password_file"
    chmod 640 "$password_file"
elif [ -e "$legacy_password_file" ]; then
    [ -s "$legacy_password_file" ] || fail 'Existing /etc/nginx/htpasswd is empty; refusing to disable authentication.'
    password_file=$legacy_password_file
elif [ "$admin_username" != admin ]; then
    fail 'Set ADMIN_PASSWORD when configuring ADMIN_USERNAME.'
else
    printf '%s\n' 'WARNING: ADMIN_PASSWORD is unset; no administrator authentication is enabled.' >&2
    : > "$auth_config"
    exit 0
fi

printf 'auth_basic "PrismLab";\nauth_basic_user_file %s;\n' "$password_file" > "$auth_config"
chmod 644 "$auth_config"
