"""Run with:  python3 -m unittest discover tests"""
import json, os, sys, tempfile, time, unittest, zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tidy

DAY = 86400


def make(root, name, data=b"x", age_days=2):
    p = os.path.join(root, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
    t = time.time() - age_days * DAY
    os.utime(p, (t, t))
    return p


def make_docx(root, name, text):
    p = os.path.join(root, name)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:t>{text}</w:t></w:document>")
    t = time.time() - 2 * DAY
    os.utime(p, (t, t))


class Args:
    min_files = 3
    archive_days = 180
    no_emoji = False


class TidyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.cats = tidy.load_categories()

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, **kw):
        a = Args()
        for k, v in kw.items():
            setattr(a, k, v)
        return {m["src"]: m for m in tidy.build_plan(self.root, self.cats, a)}

    def test_categories_valid(self):
        self.assertEqual(len(self.cats), 34)
        for c in self.cats.values():
            self.assertIn(c["finder_tag"], tidy.TAG_CODES)
            self.assertTrue(os.path.exists(os.path.join(tidy.HERE, "icons", "icns", tidy.slug(c["name"]) + ".icns")))
            if c["parent"]:
                self.assertIn(c["parent"], self.cats)

    def test_keywords_and_extensions(self):
        for i in range(3):
            make(self.root, f"IMG_{i}.jpg", bytes([i]))
            make(self.root, f"Screenshot 2026-10-0{i} at 9.41.png", bytes([10 + i]))
            make(self.root, f"track{i}.mp3", bytes([20 + i]))
        make(self.root, "2025 W2 Form.pdf", b"a")
        make(self.root, "Amazon Order Receipt.pdf", b"b")
        make(self.root, "Jane Resume.pdf", b"c")
        make(self.root, "notes.pdf", b"d")
        p = self.plan(min_files=1)
        self.assertEqual(p["IMG_0.jpg"]["category"], "Photos")
        self.assertEqual(p["Screenshot 2026-10-00 at 9.41.png"]["category"], "Screenshots")
        self.assertEqual(p["track0.mp3"]["category"], "Music")
        self.assertEqual(p["2025 W2 Form.pdf"]["category"], "Taxes")
        self.assertEqual(p["Amazon Order Receipt.pdf"]["category"], "Receipts")
        self.assertEqual(p["Jane Resume.pdf"]["category"], "Career")
        self.assertEqual(p["notes.pdf"]["category"], "Documents")

    def test_docx_content_peek(self):
        make_docx(self.root, "Document3.docx", "Course syllabus for OMIS 327, homework due Friday")
        self.assertEqual(self.plan(min_files=1)["Document3.docx"]["category"], "School")

    def test_auto_detect_folds_small_groups(self):
        make(self.root, "one.mp3", b"1")
        for i in range(3):
            make(self.root, f"p{i}.jpg", bytes([i]))
        p = self.plan()
        self.assertEqual(p["one.mp3"]["category"], "Media")  # a single song is not worth its own folder
        self.assertEqual(p["p0.jpg"]["category"], "Photos")

    def test_duplicates_and_junk(self):
        make(self.root, "report.pdf", b"same", age_days=5)
        make(self.root, "report (1).pdf", b"same", age_days=1)
        make(self.root, "~$budget.xlsx", b"lock")
        make(self.root, "empty.txt", b"")
        make(self.root, "big.zip.crdownload", b"partial", age_days=3)
        p = self.plan(min_files=1)
        self.assertEqual(p["report (1).pdf"]["category"], "Review to Delete")
        self.assertIn("Duplicates", p["report (1).pdf"]["dst"])
        self.assertNotEqual(p["report.pdf"]["category"], "Review to Delete")
        for n in ("~$budget.xlsx", "empty.txt", "big.zip.crdownload"):
            self.assertEqual(p[n]["category"], "Review to Delete", n)

    def test_archive_old_but_keep_important(self):
        make(self.root, "old_song.mp3", b"o", age_days=400)
        make(self.root, "old resume.pdf", b"r", age_days=400)
        p = self.plan(min_files=1)
        self.assertEqual(p["old_song.mp3"]["category"], "Archive")
        self.assertEqual(p["old resume.pdf"]["category"], "Career")

    def test_skips_recent_and_existing_folders(self):
        make(self.root, "fresh.pdf", b"f", age_days=0)
        os.makedirs(os.path.join(self.root, "📚 School"))
        os.makedirs(os.path.join(self.root, "My Stuff"))
        p = self.plan(min_files=1)
        self.assertNotIn("fresh.pdf", p)
        self.assertNotIn("📚 School", p)
        self.assertNotIn("My Stuff", p)

    def test_reuses_existing_folder_without_emoji(self):
        os.makedirs(os.path.join(self.root, "Photos"))
        make(self.root, "a.jpg", b"a")
        self.assertEqual(self.plan()["a.jpg"]["dst"], os.path.join("Photos", "a.jpg"))

    def test_apply_and_undo_roundtrip(self):
        for i in range(3):
            make(self.root, f"clip{i}.mov", bytes([i]))
        moves = tidy.build_plan(self.root, self.cats, Args())
        tidy.apply_plan(self.root, moves)
        self.assertTrue(os.path.exists(os.path.join(self.root, "🎞️ Videos", "clip0.mov")))
        tidy.undo_last(self.root)
        self.assertTrue(os.path.exists(os.path.join(self.root, "clip0.mov")))

    def test_resource_fork_layout(self):
        rf = tidy.resource_fork(b"icnsDATA")
        data_off, map_off, data_len, map_len = __import__("struct").unpack(">IIII", rf[:16])
        self.assertEqual(data_off, 256)
        self.assertEqual(rf[map_off + 30:map_off + 34], b"icns")
        self.assertEqual(len(rf), map_off + map_len)


if __name__ == "__main__":
    unittest.main()
