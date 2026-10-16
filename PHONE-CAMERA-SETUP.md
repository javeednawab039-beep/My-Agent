# Local phone camera companion

The companion streams camera video directly to the desktop over the same private
Wi-Fi network. There is no cloud relay, STUN/TURN server, audio stream, location
collection, contact access, or automatic app control. Hand/body detection and
person alerts run on the desktop in the existing character page. The phone page
shows only its local preview and connection state.

## Start and pair

1. Start `start-local-voice.bat` on the desktop. Keep the server running.
2. On the phone and desktop, use the same private Wi-Fi. Guest Wi-Fi or router
   client isolation may prevent the devices from seeing each other.
3. Trust the local CA on the phone as described below. This is required by
   iOS/Android browsers before they grant camera access to a local HTTPS page.
4. Open **Pair phone camera** in the desktop page. On the phone, open the exact
   `https://<desktop-LAN-IP>:8443/phone` address shown on the desktop and enter
   its one-time code. Codes expire after five minutes and cannot be reused.
5. Tap **Allow camera and connect**, then choose the camera from the selector if
   desired. Use **Disconnect phone** on the desktop or **Disconnect and stop
   camera** on the phone to end the stream.

The phone asks for camera permission only after the user presses the connect
button. Video is sent without audio using a direct WebRTC connection with no
STUN/TURN servers. Closing either page, disconnecting, ending the camera track,
or revoking permission stops the phone camera.

## Install and trust the local certificate

At startup the server creates certificates under:

`%LOCALAPPDATA%\JarvisPhoneCamera\certificates`

Only copy `phone-camera-ca.crt` to the phone. Never copy either `.key` file.
Transfer the public `.crt` file by USB, AirDrop, or another private transfer
method; do not install a certificate obtained from an untrusted source. The
server prints the exact certificate path and phone URL. If the desktop LAN IP
changes, restart the server and repeat the install/trust steps if the browser
reports a certificate error.

**iPhone/iPad (iOS):**

1. Open the transferred `phone-camera-ca.crt` on the phone and install the
   downloaded configuration profile from **Settings → Profile Downloaded**
   (or **Settings → General → VPN & Device Management**).
2. Then enable full trust under **Settings → General → About → Certificate
   Trust Settings** for **Jarvis Phone Camera Local CA**.
3. Open the printed HTTPS phone URL in Safari.

**Android:**

1. In Settings, open **Security & privacy → More security settings →
   Encryption & credentials → Install a certificate → CA certificate**. Menu
   labels vary by Android vendor/version. Select the transferred
   `phone-camera-ca.crt` and confirm the system warning.
2. Open the printed HTTPS phone URL in Chrome. If the browser does not accept
   the user-installed CA on that device/version, use a browser that honors the
   Android user CA store; do not bypass certificate warnings.

The CA is self-generated for this desktop and LAN IP. Browser TLS protects the
page and signaling; this is not a public-CA identity and should only be trusted
on devices you control.

## Windows firewall

The service binds the HTTPS and signaling listeners only to the desktop's
selected private LAN IPv4 address. The existing HTTP page and voice WebSocket
remain bound to `127.0.0.1`; their ports 8000 and 8765 are not opened to Wi-Fi.

If Windows Firewall asks, allow the local Python server on **Private networks
only**. If a rule is needed, run this in an elevated PowerShell window (replace
the executable path with the Python 3.13 executable used by `py -3.13`):

```powershell
New-NetFirewallRule -DisplayName "Jarvis phone camera (private Wi-Fi)" `
  -Direction Inbound -Action Allow -Program "C:\Path\To\Python313\python.exe" `
  -Protocol TCP -LocalPort 8443,8444 -Profile Private -RemoteAddress LocalSubnet
```

Do not enable this rule on Public networks or expose/forward these ports on the
router. The HTTPS page is on TCP 8443 and authenticated local WSS signaling is
on TCP 8444.

## Local protections and limits

Pairing codes are random, single-use, and short-lived. Signaling requires the
expected local page origin, role-bound random tokens, an eight-hour absolute
session lifetime, connection/code-attempt limits, a per-connection message
rate limit, and a 64 KiB message cap. The WebRTC peer connection uses host
candidates only (no external STUN/TURN). Stop the desktop server when finished.
