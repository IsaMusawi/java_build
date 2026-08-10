# SM DevOps Dashboard

SM DevOps Dashboard adalah utility desktop berbasis Python/Tkinter untuk
membantu proses development aplikasi Java/Maven secara lokal.

Aplikasi ini menyatukan tiga pekerjaan utama dalam satu dashboard:

1.  **Maven Build** untuk beberapa project dari VS Code
    `.code-workspace`.
2.  **Tomcat Management** untuk menjalankan beberapa instance Tomcat
    secara terpisah.
3.  **Deployment & Debugging** untuk menghubungkan artifact Maven ke
    Tomcat dan melakukan Java Remote Debug melalui VS Code.

> Aplikasi ini ditujukan untuk environment development lokal Windows,
> khususnya project Java yang menggunakan Maven, Java 8, Apache Tomcat,
> dan VS Code.

------------------------------------------------------------------------

## 1. Konsep Utama

Alur kerja aplikasi:

``` text
VS Code Workspace
       │
       ▼
┌───────────────────┐
│  Maven Build      │
│ install / clean   │
│ clean & install   │
└─────────┬─────────┘
          │
          ▼
     target artifact
     (.war / folder)
          │
          ▼
┌───────────────────┐
│ Tomcat Instance   │
│                   │
│ /email-api        │
│ /vendor-api       │
│ /common-api       │
│ /dfms-web         │
└─────────┬─────────┘
          │
          ├── START
          │
          └── DEBUG
                 │
                 ▼
             VS Code
             Java Attach
```

Satu **Tomcat instance** dapat memiliki beberapa deployment/context.

Contoh:

``` text
Tomcat-1
├── /email-api
├── /vendor-api
└── /common-api

Tomcat-2
├── /email-api
└── /dfms-web
```

Karena setiap instance dapat menggunakan port berbeda, beberapa Tomcat
dapat dijalankan bersamaan.

------------------------------------------------------------------------

# 2. Struktur Distribusi

Distribusi aplikasi yang direkomendasikan:

``` text
java_run/
├── java_run.exe
├── build_manager_settings.json
├── devops_settings.json
├── tools/
│   └── apache-maven-3.2.5/
│       ├── bin/
│       │   ├── mvn
│       │   └── mvn.bat
│       ├── boot/
│       ├── conf/
│       └── lib/
└── _internal/
    └── ...
```

Untuk source/development:

``` text
java_build/
├── main.py
├── config.py
├── path.py
├── panel_build.py
├── panel_tomcat.py
├── java_build_manager.py
├── build_manager_settings.json
├── devops_settings.json
└── tools/
    └── apache-maven-3.2.5/
```

`java_run.exe` menggunakan folder tempat executable berada sebagai base
directory. Karena itu konfigurasi dan folder `tools` tidak bergantung
pada current working directory.

------------------------------------------------------------------------

# 3. Prasyarat

## 3.1 Operating System

Target utama:

-   Windows
-   PowerShell tersedia
-   `taskkill` tersedia

Aplikasi menggunakan Windows process information untuk mendeteksi JVM
Tomcat dan menggunakan `taskkill /PID /T /F` untuk menghentikan instance
tertentu.

------------------------------------------------------------------------

## 3.2 Java

Gunakan **JDK 8**, bukan hanya JRE.

Contoh:

``` text
C:\Users\<user>\Documents\SM_TOOLS\java\jdk8u452-b09
```

Folder tersebut harus memiliki:

``` text
<JAVA_HOME>\
├── bin\
│   ├── java.exe
│   └── javac.exe
└── ...
```

Aplikasi akan menggunakan Java yang dikonfigurasi sebagai `JAVA_HOME`
saat menjalankan Maven dan Tomcat.

------------------------------------------------------------------------

## 3.3 Maven

Aplikasi menggunakan Maven dari `Maven Home` yang dikonfigurasi.

Contoh:

``` text
C:\Users\<user>\Documents\SM_TOOLS\apache-maven-3.2.5
```

Harus terdapat:

``` text
<Maven Home>\bin\mvn.cmd
```

Distribusi aplikasi juga dapat membawa Maven portable:

``` text
java_run/
└── tools/
    └── apache-maven-3.2.5/
```

Maven portable tersebut dapat digunakan tanpa memasukkan Maven ke
Windows `PATH`.

------------------------------------------------------------------------

## 3.4 Apache Tomcat

Setiap Tomcat instance harus menunjuk ke folder Tomcat yang valid.

Contoh:

``` text
C:\Users\<user>\Documents\SM_TOOLS\tomcat-server\apache-tomcat-7.0.67-dfms-api
```

Struktur minimal:

``` text
apache-tomcat-7.0.67-dfms-api/
├── bin/
├── conf/
├── lib/
├── logs/
├── temp/
├── webapps/
└── work/
```

------------------------------------------------------------------------

## 3.5 VS Code

VS Code diperlukan apabila menggunakan fitur **DEBUG**.

Aplikasi akan mencari VS Code dari:

1.  path yang tersimpan di konfigurasi;
2.  lokasi instalasi VS Code umum;
3.  command `code` pada `PATH`.

Workspace harus menggunakan file:

``` text
*.code-workspace
```

------------------------------------------------------------------------

# 4. Menjalankan Aplikasi

## 4.1 Versi EXE

Untuk distribusi:

``` text
java_run.exe
```

cukup dijalankan dengan double-click.

Tidak perlu menjalankan Python secara manual.

Pastikan struktur berikut tetap dipertahankan:

``` text
java_run.exe
tools/
└── apache-maven-3.2.5/
```

Jangan memindahkan `java_run.exe` tanpa membawa folder `tools` apabila
Maven portable ingin digunakan.

------------------------------------------------------------------------

## 4.2 Versi Source

Jika menjalankan source Python:

``` bash
python main.py
```

Pastikan dependency Python yang diperlukan tersedia, terutama:

``` text
tkinter
```

Source utama terdiri dari:

``` text
main.py
config.py
path.py
panel_build.py
panel_tomcat.py
```

------------------------------------------------------------------------

# 5. Konfigurasi Awal

Saat aplikasi dibuka, lakukan konfigurasi berikut.

## Step 1 - Pilih Workspace

Pada panel **Maven Build**:

``` text
Workspace (.code-workspace)
```

pilih file workspace VS Code.

Contoh:

``` text
C:\Users\<user>\Documents\SM_PROJECT\E-Procurement Phase 3\API\eproc-email-api.code-workspace
```

Workspace akan dibaca untuk mendapatkan daftar folder project.

Project diurutkan berdasarkan prioritas:

``` text
common-lib
bom
api
web
```

Tujuannya agar project library/BOM dapat diproses lebih dahulu sebelum
API/web.

------------------------------------------------------------------------

## Step 2 - Pilih Java 8

Isi:

``` text
Java 8 Home
```

dengan root JDK, bukan folder `bin`.

Benar:

``` text
C:\...\jdk8u452-b09
```

Salah:

``` text
C:\...\jdk8u452-b09\bin
```

------------------------------------------------------------------------

## Step 3 - Pilih Maven Home

Isi:

``` text
Maven Home
```

dengan root Maven.

Benar:

``` text
C:\...\apache-maven-3.2.5
```

Salah:

``` text
C:\...\apache-maven-3.2.5\bin
```

Aplikasi akan mencari:

``` text
<Maven Home>\bin\mvn.cmd
```

------------------------------------------------------------------------

## Step 4 - Reload Project

Klik:

``` text
Reload
```

Daftar project dari workspace akan muncul.

Contoh:

``` text
common-lib
bom
email-api
vendor-api
dfms-web
```

------------------------------------------------------------------------

# 6. Maven Build

Aplikasi menyediakan tiga operasi Maven.

  -----------------------------------------------------------------------
  Tombol                  Maven Command           Fungsi
  ----------------------- ----------------------- -----------------------
  `INSTALL`               `mvn install`           Build dan install
                                                  artifact

  `CLEAN`                 `mvn clean`             Menghapus hasil build
                                                  `target`

  `CLEAN & INSTALL`       `mvn clean install`     Clean kemudian
                                                  build/install
  -----------------------------------------------------------------------

Aplikasi juga menambahkan opsi:

``` text
-Dmaven.javadoc.skip=true
-DskipTests
-DPROJECT_ENV=LOCAL
```

Sehingga secara konseptual command yang dijalankan adalah:

``` bash
mvn install \
  -Dmaven.javadoc.skip=true \
  -DskipTests \
  -DPROJECT_ENV=LOCAL
```

Project yang dipilih akan diproses **secara sequential**, bukan paralel.

Hal ini penting untuk workspace yang memiliki dependency antar-module
seperti:

``` text
common-lib
      ↓
     bom
      ↓
     api
      ↓
     web
```

------------------------------------------------------------------------

# 7. Kapan Menggunakan INSTALL?

Untuk development sehari-hari, gunakan:

``` text
⚡ INSTALL
```

Karena operasi ini tidak melakukan `clean` terlebih dahulu.

Alur normal:

``` text
ubah source
   ↓
Maven INSTALL
   ↓
artifact diperbarui
   ↓
Deploy / Update
   ↓
Tomcat
```

Ini biasanya lebih cepat daripada selalu melakukan `clean`.

------------------------------------------------------------------------

# 8. Kapan Menggunakan CLEAN?

Gunakan:

``` text
🧹 CLEAN
```

ketika ingin menghapus hasil build sebelumnya.

Contoh situasi:

-   hasil build terasa stale;
-   dependency/artifact lama masih digunakan;
-   ingin memulai build dari kondisi bersih;
-   terdapat masalah pada folder `target`.

Perlu diperhatikan:

**CLEAN tidak menghasilkan WAR.**

`clean` hanya membersihkan hasil build.

------------------------------------------------------------------------

# 9. Kapan Menggunakan CLEAN & INSTALL?

Gunakan:

``` text
🔨 CLEAN & INSTALL
```

jika ingin memastikan artifact dibangun ulang dari awal.

Alurnya:

``` text
target lama
    ↓
mvn clean
    ↓
target dihapus
    ↓
mvn install
    ↓
artifact baru
```

Ini lebih lambat, tetapi berguna ketika build incremental memberikan
hasil yang mencurigakan.

------------------------------------------------------------------------

# 10. Deployment ke Tomcat

Setelah project berhasil di-build, gunakan panel Tomcat.

## Step 1 - Tambahkan Tomcat Instance

Klik:

``` text
➕ Add Tomcat
```

Aplikasi akan membuat instance baru, misalnya:

``` text
Tomcat-1
Tomcat-2
Tomcat-3
```

Nama instance dapat diubah dengan tombol:

``` text
✏️ Rename
```

------------------------------------------------------------------------

## Step 2 - Pilih Tomcat Home

Pada:

``` text
Server Path
```

pilih folder Tomcat.

Contoh:

``` text
C:\...\apache-tomcat-7.0.67-dfms-api
```

------------------------------------------------------------------------

## Step 3 - Atur Port

Setiap Tomcat yang berjalan bersamaan harus memiliki port yang tidak
bentrok.

Terdapat empat konfigurasi:

``` text
HTTP
AJP
Shut
Debug
```

Contoh:

### Tomcat-1

``` text
HTTP  : 8082
AJP   : 8009
Shut  : 8005
Debug : 8000
```

### Tomcat-2

``` text
HTTP  : 8083
AJP   : 8010
Shut  : 8006
Debug : 8001
```

Setelah mengubah port, klik tombol:

``` text
💾
```

Konfigurasi HTTP/AJP/shutdown akan disimpan ke:

``` text
conf/server.xml
```

Debug port disimpan melalui:

``` text
bin/setenv.bat
```

------------------------------------------------------------------------

# 11. Deployment Context

Deployment menggunakan konsep:

``` text
/context
```

Contoh:

``` text
/email-api
```

Aplikasi akan mencari artifact pada:

``` text
<project>\target\<target>
```

atau:

``` text
<project>\target\<target>.war
```

Misalnya:

``` text
email-api/
└── target/
    └── email-api.war
```

maka deployment dapat menggunakan:

``` text
Ctx: email-api
```

dan menghasilkan:

``` text
/email-api
```

------------------------------------------------------------------------

# 12. Cara Deploy / Update

Ikuti urutan berikut:

``` text
1. Pilih Maven project
       ↓
2. Pastikan artifact sudah tersedia
       ↓
3. Isi / periksa Context
       ↓
4. Klik Deploy / Update
       ↓
5. Start Tomcat
```

Contoh:

``` text
Project : email-api
Ctx     : email-api
Target  : email-api
```

Setelah deploy:

``` text
Tomcat-1
└── /email-api
```

Aplikasi membuat file:

``` text
<Tomcat Home>\conf\Catalina\localhost\email-api.xml
```

File tersebut menggunakan `docBase` yang menunjuk langsung ke artifact
hasil Maven.

------------------------------------------------------------------------

# 13. Multi Deployment

Satu Tomcat dapat menjalankan beberapa project.

Contoh:

``` text
Tomcat-1
├── /common-api
├── /email-api
├── /vendor-api
└── /dfms-web
```

Setiap deployment disimpan secara terpisah.

Contoh konfigurasi konseptual:

``` json
{
    "deployments": {
        "email-api": {
            "project": "C:\\project\\email-api",
            "target": "email-api"
        },
        "vendor-api": {
            "project": "C:\\project\\vendor-api",
            "target": "vendor-api"
        }
    }
}
```

Karena itu melakukan deploy/update satu context tidak perlu menghapus
konfigurasi deployment lainnya.

------------------------------------------------------------------------

# 14. Update Deployment

Untuk meng-update aplikasi:

``` text
Source berubah
    ↓
Maven INSTALL
    ↓
target diperbarui
    ↓
Deploy / Update
    ↓
Tomcat reload
```

Jika deployment menggunakan folder hasil build, Tomcat dapat membaca
hasil build tersebut melalui `docBase`.

Untuk perubahan yang membutuhkan restart JVM, gunakan:

``` text
⏹ STOP
    ↓
▶ START
```

------------------------------------------------------------------------

# 15. Undeploy

Pada daftar:

``` text
Deployed Applications
```

pilih deployment.

Kemudian:

``` text
🗑 Undeploy
```

Aplikasi akan menghapus:

``` text
conf/Catalina/localhost/<context>.xml
```

dan konfigurasi deployment tersebut juga dihapus dari konfigurasi
aplikasi.

Artifact Maven pada project **tidak ikut dihapus**.

------------------------------------------------------------------------

# 16. Menjalankan Tomcat

## START

Klik:

``` text
▶ START
```

Aplikasi menjalankan:

``` text
catalina.bat jpda run
```

Environment yang digunakan antara lain:

``` text
JAVA_HOME
CATALINA_HOME
PROJECT_ENV=LOCAL
```

------------------------------------------------------------------------

## DEBUG

Klik:

``` text
🐞 DEBUG
```

Mode DEBUG melakukan beberapa langkah otomatis:

``` text
1. Validasi Java
       ↓
2. Validasi Tomcat
       ↓
3. Validasi workspace
       ↓
4. Update konfigurasi Java Attach
       ↓
5. Konfigurasi JPDA
       ↓
6. Start Tomcat
       ↓
7. Tunggu debug port
       ↓
8. Buka VS Code workspace
       ↓
9. Attach debugger dari VS Code
```

------------------------------------------------------------------------

# 17. Java Remote Debug dengan VS Code

Saat DEBUG dijalankan, aplikasi menambahkan konfigurasi ke
`.code-workspace`.

Format konfigurasi yang dibuat:

``` json
{
    "type": "java",
    "name": "SM Debug | Tomcat-1",
    "request": "attach",
    "hostName": "localhost",
    "port": 8000
}
```

Konfigurasi yang dibuat aplikasi menggunakan prefix:

``` text
SM Debug |
```

Konfigurasi Java lain milik user tidak dimodifikasi.

------------------------------------------------------------------------

## Langkah Debugging

Setelah tombol:

``` text
🐞 DEBUG
```

dijalankan:

1.  Tunggu sampai log menunjukkan JPDA ready.
2.  VS Code workspace akan dibuka.
3.  Pilih konfigurasi Java attach yang dibuat untuk instance tersebut.
4.  Tekan `F5`.
5.  Pasang breakpoint pada source Java.
6.  Akses endpoint aplikasi melalui Tomcat.

Contoh:

``` text
http://localhost:8082/email-api/...
```

Debugger akan berhenti ketika breakpoint terkena.

------------------------------------------------------------------------

# 18. Menggunakan Beberapa Tomcat untuk Debug

Contoh:

``` text
Tomcat-1
HTTP  = 8082
Debug = 8000

Tomcat-2
HTTP  = 8083
Debug = 8001
```

Kemudian:

``` text
Tomcat-1
    ↓
SM Debug | Tomcat-1
    ↓
localhost:8000

Tomcat-2
    ↓
SM Debug | Tomcat-2
    ↓
localhost:8001
```

Dengan demikian debugger dapat diarahkan ke instance yang tepat.

**Jangan menggunakan debug port yang sama untuk dua Tomcat yang berjalan
bersamaan.**

------------------------------------------------------------------------

# 19. Menghentikan Tomcat

Gunakan:

``` text
⏹ STOP
```

Aplikasi tidak menggunakan:

``` text
taskkill /IM java.exe
```

karena cara tersebut dapat menghentikan aplikasi Java lain.

Sebaliknya, aplikasi mencari JVM Tomcat berdasarkan:

-   process name;
-   `org.apache.catalina.startup.Bootstrap`;
-   `catalina.home`;
-   hubungan parent/child process jika tersedia.

Kemudian hanya PID Tomcat yang ditemukan yang dihentikan.

Ini penting jika komputer sedang menjalankan:

``` text
Tomcat
VS Code Java
Maven
IDE
Java application lain
```

secara bersamaan.

------------------------------------------------------------------------

# 20. Menghapus Tomcat Instance

Jika terdapat lebih dari satu instance, tombol:

``` text
🗑 Remove
```

dapat digunakan.

Aplikasi akan:

1.  Memastikan instance bukan Tomcat terakhir.
2.  Memastikan Tomcat tidak sedang berjalan.
3.  Menghapus konfigurasi deployment instance.
4.  Menghapus konfigurasi VS Code debug yang dibuat aplikasi untuk
    instance tersebut.
5.  Menghapus instance dari daftar aktif.

Tomcat instance terakhir **tidak dapat dihapus**.

Jadi aplikasi selalu mempertahankan minimal satu instance.

------------------------------------------------------------------------

# 21. File Konfigurasi

Aplikasi menggunakan dua file konfigurasi utama.

## `build_manager_settings.json`

Digunakan untuk menyimpan konfigurasi build manager lama/kompatibilitas.

Contoh informasi:

``` json
{
    "workspace_path": "...",
    "java_home": "..."
}
```

------------------------------------------------------------------------

## `devops_settings.json`

Digunakan oleh dashboard utama.

Informasi yang disimpan antara lain:

``` text
workspace_path
java_home
maven_home
tomcat_home
vscode_path
active_tabs
deploy_map
```

Contoh struktur:

``` json
{
    "workspace_path": "...",
    "java_home": "...",
    "maven_home": "...",
    "tomcat_home": "...",
    "vscode_path": "...",
    "active_tabs": [
        "email-api"
    ],
    "deploy_map": {
        "email-api": {
            "tomcat_home": "...",
            "deployments": {
                "email-api": {
                    "project": "...",
                    "target": "email-api"
                }
            }
        }
    }
}
```

Konfigurasi ini dibuat otomatis oleh aplikasi. Tidak perlu diedit manual
kecuali untuk troubleshooting.

------------------------------------------------------------------------

# 22. Workspace VS Code

Workspace digunakan sebagai sumber daftar project.

Contoh:

``` json
{
    "folders": [
        {
            "path": "../common-lib"
        },
        {
            "path": "../bom"
        },
        {
            "path": "../email-api"
        },
        {
            "path": "../dfms-web"
        }
    ]
}
```

Aplikasi akan mengubah relative path menjadi absolute path berdasarkan
lokasi file `.code-workspace`.

------------------------------------------------------------------------

# 23. Backup Workspace Saat Debug

Sebelum aplikasi mengubah `.code-workspace` untuk menambahkan
konfigurasi debug, aplikasi membuat backup:

``` text
<workspace>.code-workspace.bak
```

Backup tersebut merepresentasikan kondisi workspace sebelum perubahan
terakhir oleh aplikasi.

Jika konfigurasi workspace mengalami masalah, file `.bak` dapat
digunakan untuk memulihkan kondisi sebelumnya.

------------------------------------------------------------------------

# 24. Alur Development yang Direkomendasikan

Untuk pekerjaan sehari-hari, gunakan alur berikut.

## A. Pertama kali setup

``` text
Open Dashboard
      ↓
Set Workspace
      ↓
Set Java 8
      ↓
Set Maven Home
      ↓
Add / Configure Tomcat
      ↓
Set Port
      ↓
Save
```

------------------------------------------------------------------------

## B. Build

``` text
Select project
      ↓
INSTALL
      ↓
Build success?
   ┌──┴──┐
  No    Yes
  ↓      ↓
Fix    Deploy
code     ↓
       Start
```

------------------------------------------------------------------------

## C. Development dengan Debugger

``` text
Modify Java source
      ↓
Maven INSTALL
      ↓
Deploy / Update
      ↓
DEBUG
      ↓
VS Code
      ↓
F5 / Attach
      ↓
Breakpoint
```

------------------------------------------------------------------------

## D. Jika Build Bermasalah

Gunakan:

``` text
CLEAN & INSTALL
```

kemudian:

``` text
Deploy / Update
```

dan restart Tomcat bila diperlukan.

------------------------------------------------------------------------

# 25. Troubleshooting

## Maven tidak ditemukan

Periksa:

``` text
Maven Home
```

Pastikan:

``` text
<Maven Home>\bin\mvn.cmd
```

benar-benar ada.

Contoh:

``` text
apache-maven-3.2.5/
└── bin/
    └── mvn.cmd
```

------------------------------------------------------------------------

## Java tidak valid

Pastikan `Java 8 Home` menunjuk ke root JDK:

``` text
jdk8u452-b09/
└── bin/
    ├── java.exe
    └── javac.exe
```

Jangan menunjuk langsung ke:

``` text
...\bin
```

------------------------------------------------------------------------

## Project tidak muncul

Periksa:

1.  File `.code-workspace` benar.
2.  Workspace berisi `folders`.
3.  Path folder masih valid.
4.  Klik `Reload`.

Jika project tidak memiliki `pom.xml`, project tersebut akan dilewati
ketika operasi Maven dijalankan.

------------------------------------------------------------------------

## Artifact tidak ditemukan saat Deploy

Periksa:

``` text
<project>\target\
```

Aplikasi mencari:

``` text
target/<target>
```

atau:

``` text
target/<target>.war
```

Jika belum ada, lakukan:

``` text
INSTALL
```

terlebih dahulu.

------------------------------------------------------------------------

## Port Tomcat bentrok

Pastikan setiap instance menggunakan port berbeda.

Contoh yang benar:

``` text
Tomcat-1
HTTP  8082
Debug 8000

Tomcat-2
HTTP  8083
Debug 8001
```

Jangan:

``` text
Tomcat-1 HTTP 8082
Tomcat-2 HTTP 8082
```

------------------------------------------------------------------------

## DEBUG tidak bisa attach

Periksa secara berurutan:

``` text
1. Tomcat berhasil start?
2. Debug port benar?
3. Debug port tidak dipakai aplikasi lain?
4. setenv.bat berisi JPDA_ADDRESS?
5. VS Code menggunakan konfigurasi instance yang benar?
```

Contoh:

``` text
JPDA_ADDRESS=8000
```

dan VS Code:

``` text
port: 8000
```

------------------------------------------------------------------------

## Tomcat sebelumnya masih hidup

Jika dashboard mengatakan instance masih berjalan, jangan langsung
menggunakan:

``` text
taskkill /IM java.exe
```

karena dapat membunuh proses Java lain.

Gunakan tombol:

``` text
STOP
```

Jika aplikasi sudah tertutup tetapi JVM Tomcat masih hidup, identifikasi
PID JVM Tomcat berdasarkan command line/catalina home sebelum
menghentikannya.

------------------------------------------------------------------------

# 26. Catatan Penting

### `CLEAN` bukan `INSTALL`

``` text
CLEAN
```

hanya membersihkan hasil build.

``` text
INSTALL
```

melakukan build dan install artifact ke Maven repository.

``` text
CLEAN & INSTALL
```

melakukan keduanya secara berurutan.

------------------------------------------------------------------------

### Deploy bukan Build

Deployment hanya menggunakan artifact yang sudah tersedia.

Jika source Java berubah, lakukan:

``` text
INSTALL
```

sebelum:

``` text
Deploy / Update
```

------------------------------------------------------------------------

### Satu Tomcat dapat memiliki banyak deployment

Tidak perlu membuat satu Tomcat untuk setiap API.

Contoh:

``` text
Tomcat-1
├── email-api
├── common-api
├── vendor-api
└── dfms-web
```

Gunakan beberapa Tomcat hanya ketika memang membutuhkan
environment/runtime/port yang terpisah.

------------------------------------------------------------------------

# 27. Arsitektur Source

Komponen utama:

``` text
main.py
   │
   ├── BuildPanel
   │      └── Maven build lifecycle
   │
   └── TomcatPanel
          ├── Tomcat lifecycle
          ├── deployment
          ├── port management
          ├── JPDA
          └── VS Code debug

config.py
   └── configuration persistence

path.py
   └── application/runtime path resolution
```

### `main.py`

Menangani:

-   main window;
-   layout;
-   Maven panel;
-   Tomcat instance selector;
-   add/remove/rename Tomcat;
-   global logging.

### `panel_build.py`

Menangani:

-   workspace project discovery;
-   Java configuration;
-   Maven configuration;
-   `install`;
-   `clean`;
-   `clean install`;
-   post-build `ws.properties` patch.

### `panel_tomcat.py`

Menangani:

-   Tomcat home;
-   port configuration;
-   deployment;
-   undeployment;
-   start;
-   debug;
-   stop;
-   process detection;
-   VS Code attach workflow.

### `config.py`

Menangani:

-   persistent configuration;
-   workspace project parsing;
-   Tomcat instance;
-   multi-deployment mapping;
-   VS Code debug configuration;
-   Maven configuration.

### `path.py`

Menentukan application directory sehingga konfigurasi dan folder `tools`
dapat dicari relatif terhadap aplikasi/EXE.

------------------------------------------------------------------------

# 28. Quick Reference

  Kebutuhan                Tombol
  ------------------------ -------------------
  Memuat ulang project     `Reload`
  Pilih semua project      `All`
  Hapus pilihan project    `None`
  Build normal             `INSTALL`
  Hapus `target`           `CLEAN`
  Build dari awal          `CLEAN & INSTALL`
  Tambah Tomcat            `Add Tomcat`
  Ganti nama instance      `Rename`
  Deploy/update artifact   `Deploy / Update`
  Hapus deployment         `Undeploy`
  Jalankan Tomcat          `START`
  Jalankan Tomcat + JPDA   `DEBUG`
  Hentikan Tomcat          `STOP`
  Hapus Tomcat instance    `Remove`

------------------------------------------------------------------------

# 29. Recommended Daily Workflow

Untuk development normal, gunakan pola sederhana ini:

``` text
┌──────────────────────┐
│ Edit Source          │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ Maven INSTALL        │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ Deploy / Update      │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ START / DEBUG        │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ Test API / Debug     │
└──────────┬───────────┘
           │
           └──────→ Edit Source
```

Jika hasil build terasa tidak konsisten:

``` text
CLEAN & INSTALL
      ↓
Deploy / Update
      ↓
Restart Tomcat
```

Dengan alur ini, proses development Maven → artifact → Tomcat → VS Code
debugger tetap berada dalam satu jalur yang jelas, tanpa perlu
menari-nari di antara terminal, Explorer, dan konfigurasi manual.
