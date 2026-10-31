# CompLens: deploy guide (always-on Docker server)

*Rewritten on 31 Oct 2026. The old version targeted Vercel. This one is for a small always-on server, which is what an app with PyTorch + EasyOCR actually needs. Written for PyCharm users: Git is done with buttons.*

You do **not** need to understand Docker or Linux to follow this. Every command is copy-paste. If a step says "expect", compare what you see with it. If it differs, go to **Section 13 (Problems and fixes)**.

---

## Contents

0. [Why we moved off Vercel, and what we chose](#0-why-we-moved-off-vercel-and-what-we-chose)
1. [What you need before you start](#1-what-you-need-before-you-start)
2. [Step 1: Supabase (database)](#2-step-1-supabase-database)
3. [Step 2: Put the code on GitHub (PyCharm buttons)](#3-step-2-put-the-code-on-github-with-pycharm-buttons-no-commands)
4. [Step 3: Rent the server](#4-step-3-rent-the-server) (**no money? see 4.3 and 4.4**)
5. [Step 4: Connect to the server](#5-step-4-connect-to-the-server)
6. [Step 5: Set the server up (one time)](#6-step-5-set-the-server-up-one-time)
7. [Step 6: Fill in your settings (.env)](#7-step-6-fill-in-your-settings-env)
8. [Step 7: Start CompLens](#8-step-7-start-complens)
9. [Step 8: Test it](#9-step-8-test-it)
10. [Step 9 (recommended): free https address](#10-step-9-recommended-free-https-address)
11. [Daily use: update, logs, restart, stop](#11-daily-use-update-logs-restart-stop)
12. [Do and don't](#12-do-and-dont)
13. [Problems and fixes](#13-problems-and-fixes)
14. [Saving money](#14-saving-money)
15. [Test it on your own laptop first (optional)](#15-test-it-on-your-own-laptop-first-optional)
16. [Using a different host with these same files](#16-using-a-different-host-with-these-same-files)
17. [Where the research came from](#17-where-the-research-came-from)

---

## How it all fits together (read this first)

```
 YOUR LAPTOP (PyCharm)          GITHUB (free)            AZURE SERVER (always on)          EVERYONE
 you edit the code     --->     stores your code  --->   runs CompLens 24/7        --->     opens your link
 click Commit + Push            (like Google Drive        (a computer in a data            https://complens.duckdns.org
                                 for code)                 centre, NOT your laptop)         on any phone
```

- **Your laptop does not need to be on.** Once the server is running, you can close the laptop and even switch it off. The site stays up. That is the whole point of the server.
- **The server gives you a link.** First it is `http://20.198.x.x` (the server's address). Then, in Section 10, you make it a nice free name like `https://complens.duckdns.org`. **That is the link you share with everyone.**
- **Git is done by clicking buttons in PyCharm** (Section 3). You never type Git commands on your laptop.
- On the **server** you paste a few commands one time (copy-paste, nothing to understand). You can do it inside PyCharm's own Terminal tab (Section 5).

---

## 0. Why we moved off Vercel, and what we chose

**The problem.** Vercel runs your app as a *function*: it switches the app off when nobody uses it, and switches it back on at the next visit. For CompLens, "switching on" means loading PyTorch and the OCR models (about 2 GB). That is the 1+ minute wait you saw, and it happens again after every idle period.

**The fix.** Run CompLens on a small **always-on server** (a "VPS"). The app starts once, loads the OCR models once, and then just stays running. Nobody waits for a restart. This is also what the code now does on start-up: it loads the OCR models in the background immediately, so even the very first scan is quick.

**What I checked (prices and rules as of 31 Oct 2026; they change, so confirm on the provider's page before paying):**

| Host | Cost for ~2-4 GB, always on | Verdict for CompLens |
|---|---|---|
| Vercel (before) | Free = 2 GB max, Pro = 4 GB | Switches off when idle, so slow restarts. This was the problem. |
| Hugging Face Spaces | Used to be free with 16 GB | **Docker Spaces became paid-only in July 2026** (PRO, about $9/month). The old guide recommended this; it no longer works for free. |
| Render | Free = 512 MB (too small). 2 GB = $25/month | Too small or too pricey. |
| Railway | RAM costs $10 per GB per month, so about $20/month for 2 GB | Always on, easy, but pricey. |
| Fly.io | 2 GB = about $13/month, no free tier, card needed | Fine, but command-line only and paid. |
| Hetzner (CX23, 4 GB) | about EUR 5.49/month | Best value, but Europe only, and in Sept-Oct 2026 new orders were reported blocked. |
| **Oracle Cloud "Always Free"** | **Free**: 2 CPU + 12 GB (cut from 24 GB in June 2026) | Free and powerful, but card needed, "no capacity" errors are common, idle servers can get switched off. |
| **Azure for Students** | **$100 credit, no credit card** | Good for the hackathon period (about 2-3 months of a 4 GB server). |
| **Vultr (Bangalore)** | 4 GB = about $24/month | Paid, but simple, reliable, and the server is in Bangalore (fast for you). |

**My recommendation: one always-on server with 4 GB RAM, running these files with Docker.** Which company you rent it from is your choice, and every step from Section 5 onward is **identical** on all of them:

- **No card, you are a college student** -> Azure for Students.
- **You have a card and want free** -> Oracle Always Free (try it; if it says "out of capacity" or refuses signup, use the next one).
- **You will pay for reliability** -> Vultr Bangalore, 4 GB.

How memory works, so you pick the right size:

| Server RAM | Setting in `.env` | Notes |
|---|---|---|
| 4 GB or more | `OCR_MAX_PASSES=3` (default) | Best accuracy. Uses about 3 GB when warmed up. |
| 2 GB | `OCR_MAX_PASSES=1` | Works, a bit less accurate on hard photos. Setup script adds swap. |
| 1 GB | not supported | PyTorch + EasyOCR will not fit. |

---

## 1. What you need before you start

- [ ] A **GitHub** account (free).
- [ ] A **Supabase** account (free).
- [ ] A way to pay or get credit for a server (Section 4).
- [ ] A computer with a terminal: **Windows** -> use *PowerShell* or *Git Bash*; **Mac/Linux** -> *Terminal*.
- [ ] About **1 hour** the first time (most of it waiting for the first build).

---

## 2. Step 1: Supabase (database)

The app works without Supabase (scans are just not saved), but you chose it, so set it up. If you already did this for Vercel, **skip to Step 2: your database is the same**, keep your keys.

1. Go to **supabase.com** -> **New project**. Pick a region near you (**Mumbai**). Save the database password somewhere.
2. Open **SQL Editor** -> **New query**. Paste the *entire* contents of `supabase/schema.sql` -> press **Run**. You should see "Success". This creates:
   - the `scans` table,
   - a **private** bucket called `label-images` for the photos,
   - the rule **"only the last 10 scans are kept"** (scan 11 deletes scan 1 and its photo).
3. Open **Project Settings -> API**. Copy two things into a notepad:
   - **Project URL** (looks like `https://abcdxyz.supabase.co`)
   - **service_role** key (very long, starts with `eyJ`; a newer key starting `sb_secret_` also works)

> **Treat the service_role key like a password.** It can read and delete everything in your project. It goes **only** into the `.env` file on the server (Step 6). Never into GitHub, never into the web page, never in a screenshot or chat.

---

## 3. Step 2: Put the code on GitHub (with PyCharm buttons, no commands)

GitHub is just a free online storage for your code. The server will download your code from there.

**A. Open the project in PyCharm**
1. Unzip the zip. You get a folder called `complens`.
2. PyCharm -> **File -> Open** -> choose that `complens` folder -> **OK** (choose *Trust Project* if asked).

**B. Log in to GitHub inside PyCharm (one time)**
1. Press **Ctrl+Alt+S** (Settings) -> **Version Control -> GitHub**.
2. Click **+** -> **Log In via GitHub**. Your browser opens; click **Authorize**. Back in PyCharm click **OK**.

**C. Create the repository and upload (one time)**
1. Top menu: **Git -> GitHub -> Share Project on GitHub**.
   - Don't see it? First do **Git -> Create Git Repository** (older PyCharm: **VCS -> Enable Version Control Integration -> Git**), select the `complens` folder, then try again.
2. In the box: **Repository name** = `complens`. **Choose Public** (see the note below). Remote name stays `origin`. Click **Share**.
3. A list of files to add appears. **Look through it: `.env` must NOT be in the list** (it is blocked on purpose, so it will not be). Click **Add**. PyCharm uploads everything.
4. A message in the bottom corner says the project was shared. Open github.com in your browser; you should see your `complens` repository with the files.

> **Why Public?** It makes the server step easy: the server can download a public repo with no password. Your code contains **no secrets**, because the Supabase key lives only in the `.env` file on the server, which is never uploaded. If you prefer Private, that works too, but then the server needs a GitHub "token" (see the Private note in Section 6).

**D. Later, when you change the code (every time)**
1. Press **Ctrl+K** (Commit). Tick the files you changed. Type a short message like `fixed label text`.
2. Click the arrow next to **Commit** and choose **Commit and Push...** -> **Push**.
3. Then update the server with **one** command (Section 11): `bash deploy/update.sh`.

**What if PyCharm shows an `.idea` folder or a `.venv` folder in the commit list?** Don't tick them. They are blocked already, so they normally don't show.

**Prefer typing commands instead?** The same thing in a terminal, inside the `complens` folder:

```bash
git init
git add .
git commit -m "CompLens on Docker server"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/complens.git
git push -u origin main
```

> **No GitHub at all?** Skip it and copy the zip straight to the server (Option B in Section 6). GitHub is easier for updates.

---

## 4. Step 3: Rent the server

### 4.1 The settings to choose (the same everywhere)

| Setting | Choose |
|---|---|
| Operating system | **Ubuntu 24.04 LTS** (64-bit). 22.04 also works. |
| Memory (RAM) | **4 GB** (2 GB is the absolute minimum) |
| CPU | 2 vCPU |
| Disk | 30 GB or more (the Docker image alone is about 3-4 GB) |
| Location | **Bangalore / Mumbai / Hyderabad** (closest to you), or Singapore |
| Login | **SSH key** (safer) or password, whichever the provider offers |
| Public IP | Yes (needed so people can open the site) |

Write down: the server's **public IP address** (like `203.0.113.25`), and the **username** (often `ubuntu` or `root`).

### 4.2 Provider notes

**Azure for Students (no credit card).** *Full click-by-click version is in section 4.3 below.*
1. Go to **azure.microsoft.com/free/students**, sign in with your **college email**. The page says it is for full-time university students and gives **$100 credit** with no card.
2. Portal -> **Create a resource -> Virtual machine**. Image: *Ubuntu Server 24.04 LTS*. Size: **B2s or B2als_v2 (2 vCPU, 4 GB)**. Region: **Central India**. Authentication: SSH public key (let Azure generate it and **download the .pem file**), username `azureuser`.
3. Inbound ports: tick **SSH (22), HTTP (80), HTTPS (443)**.
4. A 4 GB VM costs very roughly $30-40 per month pay-as-you-go (check the Azure price calculator), so $100 lasts about 2-3 months. **When you are not demoing, press "Stop" on the VM** in the portal: a stopped (deallocated) VM stops charging for compute. Starting it again takes about a minute, and the site is back with models loaded within 2 minutes.

**Oracle Cloud Always Free (free, but fiddly)**
1. Sign up at **oracle.com/cloud/free**. It needs a card and a phone number (no prepaid cards). Choose home region **India South (Hyderabad)** or **India West (Mumbai)**. You cannot change the region later.
2. **Compute -> Instances -> Create instance**. Image: *Canonical Ubuntu 24.04* (the ARM version). Shape: **Ampere VM.Standard.A1.Flex, 2 OCPU, 12 GB** (the free limit since June 2026). Download the **private key** when offered. Username is `ubuntu`.
3. **"Out of host capacity" error?** Very common. Try another availability domain, try a smaller shape (1 OCPU / 6 GB with `OCR_MAX_PASSES=1`), or try again in a few hours.
4. Open ports: **Networking -> Virtual Cloud Networks -> your VCN -> Security Lists -> Default -> Add Ingress Rules**: source `0.0.0.0/0`, TCP, destination port `80`; add another for `443`.
5. Oracle has been reported to switch off free servers that sit idle (low CPU use) for 7 days. Upgrading the account to *Pay As You Go* (you stay free if you stay inside the free limits) is the commonly reported way to avoid this. Check Oracle's current rules.
6. These files build for ARM too (PyTorch publishes ARM CPU builds). I could not test an ARM build myself, so if the build fails there, send me the error log.

**Vultr (paid, simplest)**
1. Create an account at vultr.com. **Deploy new server -> Cloud Compute -> Regular Performance** (or High Frequency for faster). Location **Bangalore**. Image **Ubuntu 24.04**. Plan **4 GB RAM (2 vCPU)**, about $24/month at the time of checking.
2. Tick *Enable IPv4*. Add your SSH key if you have one, otherwise note the root password shown on the server page.
3. Ports are open by default. If you turned on a Firewall group, allow TCP 22, 80, 443.

**DigitalOcean, Linode or any other VPS** works the same way: Ubuntu 24.04, 4 GB, a location in India or Singapore, ports 22/80/443 open.

### 4.3 FULL STEP-BY-STEP for ₹0: free Azure server (no card)

This is the path for a student with no money and no credit card. You get **$100 of free credit**. A 4 GB server costs very roughly $30-40 a month while it is switched on, so if it runs all day the credit lasts 2-3 months, and much longer if you switch it off between demos. You can renew it each year while you are a student.

**A. Get the free student credit (about 10 minutes)**
1. Open **azure.microsoft.com/free/students** and click the button to start.
2. Sign in with a Microsoft account (any email; click "Create one" if you have none).
3. It asks you to **verify you are a student**. Use your **college email** (the one ending in your college's domain). Microsoft sends a code to that inbox. If your college email is not accepted, it may offer another proof option (follow the screen).
4. **No credit card is asked.** When it finishes you have an "Azure for Students" subscription.

> I could not confirm for you that Microsoft accepts every college in India. If verification fails, do **section 4.4** (laptop) instead. It is also free.

**B. Create the server (about 10 minutes)**
1. Go to **portal.azure.com** (sign in with the same account).
2. In the top search box type **Virtual machines**, open it, click **Create -> Azure virtual machine**.
3. Fill the form:
   - **Subscription:** Azure for Students
   - **Resource group:** click *Create new*, name it `complens-rg`
   - **Virtual machine name:** `complens-vm`
   - **Region:** **Central India**. Student accounts often allow only some regions. If Central India gives an error or has no sizes, try **South India**, then **Southeast Asia**.
   - **Availability options:** No infrastructure redundancy required
   - **Image:** **Ubuntu Server 24.04 LTS - x64 Gen2**
   - **Size:** click *See all sizes*, search **B2s** (2 vCPU, 4 GiB RAM) or **B2als_v2**, choose one. If neither is listed for students, pick any size with **4 GiB RAM** and 2 vCPU.
   - **Authentication type:** SSH public key
   - **Username:** `azureuser`
   - **SSH public key source:** *Generate new key pair*, key pair name `complens-key`
   - **Public inbound ports:** *Allow selected ports*, tick **SSH (22), HTTP (80), HTTPS (443)**
4. Leave the other tabs as they are. Click **Review + create**, then **Create**.
5. A box appears: **Download private key and create resource**. Click it. A file `complens-key.pem` downloads. **Keep it safe; it is your password to the server.** If you lose it you cannot log in.
6. Wait about 2 minutes, then click **Go to resource**. Copy the **Public IP address** (like `20.198.x.x`).
7. Make the IP permanent: on the VM page click **Networking**, click the **public IP address name**, open **Configuration**, and make sure **Assignment = Static**, then **Save**. (If it already says Static, nothing to do.)

**C. Log in from Windows**
1. Open **PowerShell**.
2. Windows may refuse the key ("UNPROTECTED PRIVATE KEY FILE"). Fix it once (change `YOUR-NAME` to your Windows user name and use the real path of the downloaded file):

```powershell
icacls "C:\Users\YOUR-NAME\Downloads\complens-key.pem" /inheritance:r
icacls "C:\Users\YOUR-NAME\Downloads\complens-key.pem" /grant:r "$($env:USERNAME):(R)"
```

3. Log in (use your server's IP):

```powershell
ssh -i "C:\Users\YOUR-NAME\Downloads\complens-key.pem" azureuser@20.198.x.x
```

Type `yes` when asked. You now see a prompt like `azureuser@complens-vm:~$`. **Continue with Section 6 (Step 5)** and follow the guide to the end.

**D. Do not waste the credit**
- When you are not demoing: VM page -> **Stop**. (Close the window, the app is paused and compute billing stops. Small charges for the disk and the IP address continue.) **Start** it again when you need it. It is ready about 2 minutes after starting.
- Check your balance: search **Cost Management** in the portal, or open your *Azure for Students* subscription page.
- Never leave the VM running for weeks "just in case".

### 4.4 BACKUP ONLY: run it on your laptop and share a free link

> **This is not the real plan.** The real plan is the Azure server in 4.3, which stays on by itself. Use 4.4 only if Azure refuses your college email, or for a quick demo. Here the laptop **must** stay on, and the link changes every time.

Good for a demo or a judge. The app runs **on your own laptop** and a free tunnel gives it a public web link. Limits: the laptop must stay **on and awake**, and the link changes each time you start it.

You need a laptop with **8 GB RAM** (the app uses about 3 GB) and about 10 GB free disk.

1. Install **Docker Desktop** (docker.com). On Windows it also installs WSL2; restart when asked. Open Docker Desktop and wait until it says it is running.
2. Unzip the project. In PowerShell, inside the `complens` folder:

```powershell
copy .env.example .env
notepad .env
```

   Fill `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`, save and close Notepad.
3. Build and run (first time takes 10-25 minutes, then it is quick):

```powershell
docker build -t complens .
docker run --rm -p 8000:8000 --env-file .env complens
```

   Open **http://localhost:8000**. Wait until the page stops saying "loading models".
4. In a **second** PowerShell window, install and start the free tunnel:

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:8000
```

   It prints a link like `https://something-random.trycloudflare.com`. **Anyone can open that link** while both windows stay open. Stop everything with `Ctrl+C` in both windows.
5. This tunnel is meant for testing and demos, with no uptime promise. For something that must be online all day, use Azure (4.3).

---

## 5. Step 4: Connect to the server

On your computer open a terminal and type (replace the username and IP with yours). **Easiest: use the Terminal tab inside PyCharm** (press **Alt+F12**, or click *Terminal* at the bottom). On Windows it is PowerShell, and `ssh` already works there.

```bash
ssh ubuntu@203.0.113.25
```

- If the provider gave you a key file (`.pem`): `ssh -i C:\path\to\key.pem ubuntu@203.0.113.25` (Mac/Linux: first run `chmod 600 key.pem`).
- First time it asks *"Are you sure you want to continue connecting?"* -> type `yes`.
- Typical usernames: **Oracle** `ubuntu`, **Azure** `azureuser`, **Vultr / DigitalOcean** `root`.

**Expect:** a welcome message and a prompt like `ubuntu@complens:~$`. You are now typing commands **on the server**. Everything from here to Section 11 is typed in this window.

---

## 6. Step 5: Set the server up (one time)

### Get the code onto the server

**Option A: from GitHub (recommended)**

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/YOUR-USERNAME/complens.git
cd complens
```

If you made the repository **Private**, the server needs a GitHub token. Create one at GitHub -> Settings -> Developer settings -> Personal access tokens -> Tokens (classic) -> Generate -> tick `repo`, then use it inside the address:

```bash
git clone https://YOUR-USERNAME:YOUR_TOKEN@github.com/YOUR-USERNAME/complens.git
```

**Option B: no GitHub, copy the zip**

On **your computer** (not the server), in the folder holding the zip:

```bash
scp Complens-v4.3-PyCharm-Azure.zip ubuntu@203.0.113.25:~
```

Then on the server:

```bash
sudo apt-get update && sudo apt-get install -y unzip
unzip Complens-v4.3-PyCharm-Azure.zip
cd complens
```

### Run the setup script

```bash
sudo bash deploy/setup-server.sh
```

It does four things and tells you as it goes: installs Docker, adds 4 GB swap if the server has less than 7 GB RAM (a safety net so the build never runs out of memory), and opens ports 80 and 443. **Expect** it to finish with `Done.` after 1-3 minutes.

**Now log out and in again** (this makes the `docker` permission active):

```bash
exit
```

...then run your `ssh ...` command again, and `cd complens`.

---

## 7. Step 6: Fill in your settings (.env)

```bash
cp .env.example .env
nano .env
```

`nano` is a simple text editor. Move with the arrow keys. Change **these lines** and leave the rest:

```
SITE_ADDRESS=:80
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
SUPABASE_SERVICE_KEY=paste-your-long-key-here
```

- No quotes, no spaces around `=`.
- **2 GB server?** Also change `OCR_MAX_PASSES=3` to `OCR_MAX_PASSES=1`.
- Don't want Supabase now? Leave the two Supabase lines as they are: the app still works, it just doesn't save scans.

**Save and exit nano:** press `Ctrl+O`, then `Enter`, then `Ctrl+X`.

Check it worked (shows the file, your key should be there):

```bash
cat .env
```

---

## 8. Step 7: Start CompLens

```bash
docker compose up -d --build
```

**This first build takes 10 to 25 minutes.** It downloads PyTorch and the OCR models once. You will see a lot of scrolling text; that is normal. Every build after this is quick, because the heavy parts are saved.

> If your SSH window disconnects during the build: reconnect, `cd complens`, and run the same command again. It continues from where it stopped.

**Expect at the end:** `Container complens-app-1 Started` and `Container complens-caddy-1 Started`.

Now watch the app start up:

```bash
docker compose logs -f app
```

**Expect to see**, within about a minute:

```
INFO:     Uvicorn running on http://0.0.0.0:8000
... OCR warm-up finished in 25.3 s (['en+hi', 'en'])
```

Press `Ctrl+C` to stop watching (the app keeps running). Then:

```bash
docker compose ps
```

**Expect:** `app` shows `Up ... (healthy)` and `caddy` shows `Up`.

---

## 9. Step 8: Test it

1. On your **phone or computer**, open `http://YOUR-SERVER-IP` (example: `http://203.0.113.25`). You should see the CompLens page.
2. Open `http://YOUR-SERVER-IP/health`. **Expect** something like `{"status":"ok","supabase":true,...,"ocr":{"status":"ready",...}}`.
   - `"ocr":{"status":"loading"}` -> the models are still loading; wait a minute.
   - `"supabase":false` -> the Supabase lines in `.env` are empty or wrong (see Section 13).
3. Click one of the sample labels under **Paste text** -> **Check label**. Instant result = rules engine works.
4. Scan a **real photo** of a label. It should answer in several seconds. (On a 2-CPU server, OCR can take from a few seconds up to about half a minute for a hard photo with 3 passes. That is normal. There is no 1-minute wake-up any more.)
5. In Supabase -> **Table Editor -> scans**: your scan should be there.
6. **The real proof:** leave it alone for a few hours, then scan again. It should answer right away.
7. **Reboot test:** run `sudo reboot`, wait 2 minutes, and open the site. It must come back by itself.

---

## 10. Step 9 (recommended): free https address

At `http://IP` the browser may show "Not secure", and some phones are picky about uploads from non-https sites. A free name fixes it.

1. Go to **duckdns.org**, sign in with GitHub or Google.
2. Type a name (example `complens`) -> **add domain**. In the **current ip** box put your **server's IP** -> **update ip**. You now own `complens.duckdns.org`.
3. On the server:

```bash
cd ~/complens
nano .env
```

Change the first setting to your name:

```
SITE_ADDRESS=complens.duckdns.org
```

Save (`Ctrl+O`, `Enter`, `Ctrl+X`), then:

```bash
docker compose up -d
```

4. Wait about one minute. Open **`https://complens.duckdns.org`**. Caddy gets a free certificate by itself and renews it automatically.
5. Not working? `docker compose logs caddy`. The usual cause: ports 80/443 not opened in the provider's firewall (Section 4), or the DuckDNS IP is wrong.

---

## 11. Daily use: update, logs, restart, stop

All commands are typed on the server, inside the `complens` folder (`cd ~/complens`).

| I want to... | Command |
|---|---|
| **Update** after I pushed new code to GitHub | `bash deploy/update.sh` |
| See live logs | `docker compose logs -f app` (Ctrl+C to leave) |
| Is it running? | `docker compose ps` |
| Restart the app | `docker compose restart app` |
| Stop everything | `docker compose down` |
| Start again | `docker compose up -d` |
| How much memory is used? | `free -h` and `docker stats --no-stream` |
| Free some disk space | `docker image prune -f` |

**Changing code later:** edit in PyCharm -> **Ctrl+K**, write a message, **Commit and Push** (Section 3D) -> on the server run `cd ~/complens && bash deploy/update.sh`. Changing only code rebuilds in under a minute.

**Changed `.env`?** Run `docker compose up -d` so the app picks it up.

---

## 12. Do and don't

**Do**
- Do use a **4 GB** server for the best accuracy.
- Do keep the secret key only in `.env` on the server.
- Do press **Stop** on Azure (or destroy the server on paid hosts) when you will not use it for weeks.
- Do rotate the Supabase key (Project Settings -> API) if it ever lands in GitHub, chat, or a screenshot.
- Do use `docker compose logs -f app` first when something looks wrong.

**Don't**
- Don't commit `.env` to GitHub.
- Don't run `docker system prune -a`: it deletes the saved layers and the next build takes 20 minutes again.
- Don't change `--workers 1` in the Dockerfile to a higher number. Each worker loads its own copy of the OCR models (about 1.5 GB each) and a small server runs out of memory.
- Don't pick a 1 GB server.
- Don't put private or confidential label photos through the demo: the site has **no login**, so anyone who knows the address can use it.

---

## 13. Problems and fixes

| What you see | Why | Fix |
|---|---|---|
| Browser: *can't reach / timed out* | Ports 80/443 closed in the provider firewall | Section 4: open TCP 80 and 443 (Oracle: Security List; Azure: Networking -> inbound rules). |
| `permission denied ... docker.sock` | You have not logged out and in since setup | `exit`, ssh back in. Or put `sudo` in front of the command. |
| `.env: no such file` | Not created yet | `cp .env.example .env` then `nano .env`. |
| `docker compose` says `command not found` | Docker not installed | `sudo bash deploy/setup-server.sh` again. |
| Build stops with `Killed` or exit code 137 | Ran out of memory | Check swap: `free -h` (Swap should be 4 GB). Use a bigger server, or run the setup script again. |
| Build fails at the PyTorch step on a non-x86 server | Network/architecture issue | Re-run the build once (temporary network errors). If it repeats, copy the last 30 lines of the log and ask for help. |
| `/health` says `"ocr":{"status":"failed",...}` | Models could not load | Read the error text inside it. Most often out of memory: set `OCR_MAX_PASSES=1`, then `docker compose up -d`. |
| `/health` says `"supabase":false` | Supabase lines missing or wrong in `.env` | Fix them, then `docker compose up -d`. |
| Scans work but nothing appears in Supabase | Wrong key or schema not run | Re-run `supabase/schema.sql`; check the key is the **service_role** one; look at `docker compose logs app` for "could not save scan". |
| Scan says *Out of memory* / the app restarts | RAM too small for 3 OCR passes | `OCR_MAX_PASSES=1`, or use a 4 GB server. |
| `https://` shows a certificate error | Certificate not issued yet, or DNS wrong | Wait 2 minutes. `docker compose logs caddy`. Check the DuckDNS IP and that ports 80+443 are open. |
| Page opens but is the *old* look | Browser cache | Hard refresh (Ctrl+Shift+R). |
| Very slow right after the server (re)boots | OCR models loading | Normal for the first minute. The page shows a notice; text checks work immediately. |
| Site down after Azure *Stop* then *Start* | Public IP changed | Azure -> the VM -> Networking -> set the IP to **Static**, or update the IP in DuckDNS. |

Still stuck? Send me the output of these two commands:

```bash
docker compose ps
docker compose logs --tail 60 app
```

---

## 14. Saving money

- A server bills while it exists. **Azure**: *Stop* it (deallocate) between demos. **Vultr / DigitalOcean**: *Destroy* it when finished; your code is safe on GitHub and your data in Supabase, so you can recreate it by repeating Steps 4-8 (about 40 minutes).
- After the hackathon, cancel the server. Supabase's free plan can stay.
- Cheaper **2 GB** server? It works with `OCR_MAX_PASSES=1`, just with slightly less accuracy on hard photos.

---

## 15. Test it on your own laptop first (optional)

Install **Docker Desktop**, then in the project folder:

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost`. (Port 80 busy? Run `docker build -t complens . && docker run --rm -p 8000:8000 --env-file .env complens` and open `http://localhost:8000`.) Stop with `Ctrl+C`.

Without Docker, the normal Python way still works (see README.md: `uvicorn app.main:app --reload`).

---

## 16. Using a different host with these same files

The `Dockerfile` runs on any host that runs Docker images (Railway, Fly.io, Render, Google Cloud Run, a company server). What to remember:

- Give it **at least 2 GB RAM** (4 GB for `OCR_MAX_PASSES=3`) and **keep one instance always on** (no scale-to-zero, no "sleep when idle"). Otherwise the slow restart comes back.
- Set the same environment variables as in `.env.example` in the host's settings page (`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET`, `OCR_MAX_PASSES`).
- The app listens on the port given by the `PORT` variable (default 8000). Most hosts set this for you.
- On those hosts you do not need `docker-compose.yml` or `deploy/` (the host provides https itself).

---

## 17. Where the research came from

Checked 31 Oct 2026. Please re-check prices before paying.

- Hugging Face moved Docker Spaces behind a paid plan (July 2026): [HF forum thread](https://discuss.huggingface.co/t/docker-sdk-now-marked-as-paid-when-creating-a-new-space/177580), [Spaces overview](https://huggingface.co/docs/hub/spaces-overview)
- Oracle Always Free cut to 2 OCPU / 12 GB on 15 June 2026: [InfoQ](https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/)
- Free-tier comparison (Render, Railway, Koyeb, Fly, Cloud Run, Oracle, Azure): [snapdeploy.dev](https://snapdeploy.dev/state-of-free-hosting)
- Render prices: [render.com/pricing](https://render.com/pricing.md) / Railway prices: [docs.railway.com](https://docs.railway.com/pricing/plans.md) / Fly.io prices: [docs.fly.io](https://docs.fly.io/about/pricing)
- Hetzner CX plans and June 2026 price change: [bitdoze.com](https://www.bitdoze.com/hetzner-cloud-cost-optimized-plans), [privatedevops.com](https://privatedevops.com/news/hetzner-june-2026-cloud-price-increase-what-to-do)
- Azure for Students: [azure.microsoft.com/free/students](https://azure.microsoft.com/en-us/free/students)
- Vultr prices (third-party price table, Bangalore location confirmed on vultr.com): [vultr-guide](https://vultr-guide.pages.dev/blog/article-20260615.html), [vultr.com](https://www.vultr.com/products/regular-performance-compute/)
