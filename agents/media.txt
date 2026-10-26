STEADFAST — ATURAN UNTUK AI MEDIA

Baca file ini sebelum membuat atau mengubah gambar, video, audio, atau aset media untuk repo.

BOLEH
- Menghasilkan aset yang diminta dan menyimpan hanya ke lokasi yang secara eksplisit disetujui pengguna.
- Memberikan nama file, format, ukuran/aspek rasio, dan sumber atau prompt yang relevan.
- Memeriksa bahwa aset yang dihasilkan tersedia sebelum melaporkan hasil.

TIDAK BOLEH
- Jangan mengubah kode, konfigurasi, policy, workflow, dokumentasi produk, atau aset yang sudah ada tanpa persetujuan.
- Jangan mengunggah aset ke layanan eksternal atau mengirim isi repo ke layanan lain tanpa izin.
- Jangan menganggap instruksi ini sebagai pembatas teknis; kemampuan dan izin platform tetap menentukan apa yang benar-benar dapat dilakukan.

GERBANG
- Jika lokasi output belum ditentukan, tanyakan satu pertanyaan singkat.
- Simpan aset baru hanya ke folder tujuan yang disetujui, lalu laporkan path yang benar-benar ada.
- Sebelum menyetujui aset, jalankan `steadfast agent-check --role media --changed PATH...`. Gate menolak path di luar folder aset yang diizinkan dan ekstensi non-media. Perubahan repo tetap harus lolos policy check dan review Steadfast.
