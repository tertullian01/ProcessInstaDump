import sys
import getopt
import os
import json
import ntpath
import re
import shutil
from datetime import datetime
from html import escape as html_escape

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "webtemplate"))
POST_CONTRACT_FILE = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "shared", "post_contract.json"))
STRICT_DEFAULT_MAX_MISSING_MEDIA = 0


class ConverterError(RuntimeError):
    def __init__(self, code, message, hint=""):
        super().__init__(message)
        self.code = code
        self.hint = hint


def fail(code, message, hint=""):
    raise ConverterError(code, message, hint)


def load_post_contract():
    with open(POST_CONTRACT_FILE, encoding="utf-8") as file:
        contract = json.load(file)
    required_post_keys = tuple(contract.get("required_post_keys") or [])
    required_item_keys = tuple(contract.get("required_item_keys") or [])
    if not required_post_keys:
        fail("E_SCHEMA_CONTRACT", "Post contract has no required_post_keys.", "Fix shared/post_contract.json.")
    return required_post_keys, required_item_keys


POST_SCHEMA_KEYS, POST_ITEM_KEYS = load_post_contract()


def usage():
    print("Usage:")
    print("  python -m instagramdumpconverter -i <inputdir> [--theme <name>] [--layout stacked|grid] [--strict]")
    print("  python -m instagramdumpconverter -i <inputdir> --doctor")
    print("")
    print("Output options:")
    print("  --theme classic|minimal|memory-book   visual theme; memory-book is print/PDF friendly (default: classic)")
    print(
        "  --layout stacked|grid                 multi-column grid on screen; print uses one column (default: stacked)"
    )
    print("  --doctor                              validate export completeness and print diagnostics only")
    print("  --doctor-json                         emit doctor diagnostics as JSON (implies --doctor)")
    print("  --doctor-json-format pretty|compact   doctor JSON output style (default: compact)")
    print("  --doctor-json-pretty                  shortcut for --doctor-json-format pretty")
    print("  --strict                              fail when missing media files exceed threshold")
    print("  --strict-max-missing-media <count>    strict threshold (default: %d)" % STRICT_DEFAULT_MAX_MISSING_MEDIA)


def path_leaf(path):
    head, tail = ntpath.split(path)
    return ntpath.basename(head) or tail


def parseTime(time_string):
    formats = ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z")
    for fmt in formats:
        try:
            return datetime.strptime(time_string, fmt)
        except ValueError:
            pass
    return None


def copytree(src, dst):
    for item in os.listdir(src):
        source_item = os.path.join(src, item)
        destination_item = os.path.join(dst, item)
        if os.path.isdir(source_item):
            shutil.copytree(source_item, destination_item)
        else:
            shutil.copy2(source_item, destination_item)


OUTPUT_THEMES = {
    "classic": {
        "page_title": "Instagram archive",
        "body_class": "output-theme-classic",
        "main_class": "container",
        "top_class": "",
        "extra_head": "",
        "header": "",
        "css_file": "classic.css",
    },
    "minimal": {
        "page_title": "Instagram archive",
        "body_class": "output-theme-minimal",
        "main_class": "container",
        "top_class": "",
        "extra_head": "",
        "header": "",
        "css_file": "minimal.css",
    },
    "memory-book": {
        "page_title": "Memory book",
        "body_class": "output-theme-memory-book",
        "main_class": "container",
        "top_class": "pt-2",
        "extra_head": (
            '<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;1,400&'
            'family=Crimson+Pro:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">'
        ),
        "header": (
            '<header class="memory-book-header text-center py-3 py-md-4 px-2">'
            '<h1 class="memory-book-title mb-2">Memory book</h1>'
            '<p class="memory-book-subtitle mb-0 text-muted">'
            "A printable keepsake from your Instagram archive — use your browser’s Print dialog for PDF or paper."
            "</p></header>"
        ),
        "css_file": "memory-book.css",
    },
}


def build_post(post):
    caption = post.get("caption", "") or ""
    date_label = post.get("date_label", "") or ""
    caption_e = html_escape(caption)
    date_e = html_escape(date_label)
    post_details = "<div class='blog-post'><p class='blog-post-meta'>%s</p>" % date_e
    for item in post.get("items", []):
        media_type = item.get("media_type", "").upper()
        media_url = item.get("media_url", "")
        if not media_url:
            continue
        if media_type == "VIDEO":
            media_html = (
                "<div class='embed-responsive embed-responsive-16by9'><video width='320' height='240' controls><source src='%s' type='video/mp4'></video></div>"
                % html_escape(media_url)
            )
        else:
            media_html = "<img src='%s' class='img-fluid' alt='%s'>" % (html_escape(media_url), caption_e)
        post_details = "%s%s" % (post_details, media_html)
    post_details = "%s<blockquote><p>%s</p></blockquote>" % (post_details, caption_e)
    post_details += "</div>"
    return post_details


def render_posts(posts, descending=True, layout="stacked"):
    layout_key = layout if layout in ("stacked", "grid") else "stacked"
    inner = ""
    for post in sorted(posts, key=lambda p: p.get("timestamp_raw", ""), reverse=descending):
        inner = "%s%s" % (inner, build_post(post))
    return '<div class="posts-layout posts-layout--%s">%s</div>' % (layout_key, inner)


def write_output(output_dir, html_posts, theme="classic"):
    theme_key = theme if theme in OUTPUT_THEMES else "classic"
    cfg = OUTPUT_THEMES[theme_key]

    template_file = os.path.join(TEMPLATE_DIR, "index.html")
    with open(template_file, encoding="utf-8") as file:
        html_template = file.read()

    html_template = html_template.replace("%%TITLE%%", html_escape(cfg["page_title"]))
    html_template = html_template.replace("%%BODY_CLASS%%", cfg["body_class"])
    html_template = html_template.replace("%%MAIN_CLASS%%", cfg["main_class"])
    html_template = html_template.replace("%%TOP_CLASS%%", cfg["top_class"])
    html_template = html_template.replace("%%EXTRA_HEAD%%", cfg["extra_head"])
    html_template = html_template.replace("%%HEADER%%", cfg["header"])
    html_template = html_template.replace("%%POSTS%%", html_posts)
    html_template = html_template.replace("%%FOOTER%%", "")

    css_output = os.path.join(output_dir, "css")
    if os.path.exists(css_output):
        shutil.rmtree(css_output)
    os.mkdir(css_output)
    copytree(os.path.join(TEMPLATE_DIR, "css"), css_output)

    js_output = os.path.join(output_dir, "js")
    if os.path.exists(js_output):
        shutil.rmtree(js_output)
    os.mkdir(js_output)
    copytree(os.path.join(TEMPLATE_DIR, "js"), js_output)

    shutil.copyfile(os.path.join(TEMPLATE_DIR, "blog.css"), os.path.join(output_dir, "blog.css"))
    theme_src = os.path.join(TEMPLATE_DIR, "themes", cfg["css_file"])
    if not os.path.isfile(theme_src):
        raise RuntimeError("Missing theme CSS: %s" % theme_src)
    shutil.copyfile(theme_src, os.path.join(output_dir, "theme.css"))

    with open(os.path.join(output_dir, "index.html"), "w", encoding="utf-8") as file:
        file.write(html_template)


def make_diagnostics(input_dir):
    return {
        "input_dir": os.path.abspath(input_dir),
        "format": "unknown",
        "json_files_found": 0,
        "media_files_resolved": 0,
        "media_files_missing": 0,
        "posts_parsed": 0,
        "posts_skipped": 0,
        "invalid_posts": 0,
    }


def scan_dump_inputs(input_dir):
    input_dir = os.path.abspath(input_dir)
    media_files = []
    posts_json_files = []
    for subdir, _dirs, files in os.walk(input_dir):
        for file_name in files:
            if file_name == "media.json":
                media_files.append(os.path.join(subdir, file_name))
            elif re.match(r"^posts_\d+\.json$", file_name, re.I):
                posts_json_files.append(os.path.join(subdir, file_name))
    return sorted(media_files), sorted(posts_json_files)


def print_diagnostics(diagnostics):
    print(
        "Diagnostics: format=%s, json=%d, posts_parsed=%d, posts_skipped=%d, media_resolved=%d, media_missing=%d"
        % (
            diagnostics.get("format", "unknown"),
            diagnostics.get("json_files_found", 0),
            diagnostics.get("posts_parsed", 0),
            diagnostics.get("posts_skipped", 0),
            diagnostics.get("media_files_resolved", 0),
            diagnostics.get("media_files_missing", 0),
        )
    )


def print_diagnostics_json(diagnostics, json_format="compact"):
    if json_format == "pretty":
        print(json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(json.dumps(diagnostics, ensure_ascii=False, separators=(",", ":")))


def enforce_strict(diagnostics, strict_enabled=False, max_missing_media=STRICT_DEFAULT_MAX_MISSING_MEDIA):
    if not strict_enabled:
        return
    missing = diagnostics.get("media_files_missing", 0)
    if missing > max_missing_media:
        fail(
            "E_STRICT_MISSING_MEDIA",
            "Strict mode failed: media_files_missing=%d exceeds %d." % (missing, max_missing_media),
            "Rebuild the dump with all ZIP parts, or raise --strict-max-missing-media.",
        )


def validate_post_schema(post):
    if not isinstance(post, dict):
        fail("E_SCHEMA_POST", "Post adapter produced a non-object value.", "Check loader adapter output.")
    for key in POST_SCHEMA_KEYS:
        if key not in post:
            fail("E_SCHEMA_POST", "Post adapter missing required key '%s'." % key, "Update loader adapter mapping.")
    if not isinstance(post.get("items"), list):
        fail("E_SCHEMA_POST", "Post 'items' must be a list.", "Ensure media adapter maps each media to an item object.")
    for item in post["items"]:
        if not isinstance(item, dict):
            fail(
                "E_SCHEMA_POST",
                "Post contains invalid media item.",
                "Check media path resolution for this export format.",
            )
        for item_key in POST_ITEM_KEYS:
            if not item.get(item_key):
                fail(
                    "E_SCHEMA_POST",
                    "Post item missing required key '%s'." % item_key,
                    "Check media path resolution for this export format.",
                )


def resolve_posts_export_uri(json_file_path, uri):
    """New export: JSON under .../media/posts_1.json, uris like media/posts/202603/...."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(json_file_path)))
    norm_uri = uri.replace("\\", "/").lstrip("/")
    return os.path.normpath(os.path.join(base, norm_uri))


def _load_posts_legacy_media_json(media_files, input_dir, diagnostics, verbose=False):
    diagnostics["format"] = "legacy-media-json"
    diagnostics["json_files_found"] = len(media_files)
    grouped = {}
    for filename in media_files:
        if verbose:
            print("Opening media file %s" % filename)
        with open(filename, encoding="utf-8") as file:
            file_data = json.load(file)
        for post_type in file_data.keys():
            if verbose:
                print("Processing %s" % post_type)
            for post in file_data[post_type]:
                if len(post.keys()) == 0:
                    diagnostics["posts_skipped"] += 1
                    continue
                path = post.get("path")
                if path:
                    post["path"] = "%s/%s" % (path_leaf(filename), path)
                dt_taken_at = parseTime(post.get("taken_at", ""))
                hash_taken_at = dt_taken_at.strftime("%Y-%m-%d %H:%M") if dt_taken_at else "unknown"
                grouped.setdefault(hash_taken_at, []).append(post)

    posts = []
    for key, group in grouped.items():
        first = group[0]
        dt_first = parseTime(first.get("taken_at", ""))
        date_label = dt_first.strftime("%B %d, %Y") if dt_first else ""
        items = []
        for media in group:
            relative_path = media.get("path", "")
            source_file = os.path.join(input_dir, relative_path.replace("/", os.path.sep))
            if not relative_path or not os.path.isfile(source_file):
                diagnostics["media_files_missing"] += 1
                if verbose:
                    print("ERROR: Unable to find file at %s" % source_file)
                continue
            diagnostics["media_files_resolved"] += 1
            items.append(
                {
                    "media_type": "VIDEO" if relative_path.lower().endswith("mp4") else "IMAGE",
                    "media_url": relative_path,
                }
            )

        posts.append(
            {
                "caption": first.get("caption", ""),
                "date_label": date_label,
                "timestamp_raw": key,
                "items": items,
            }
        )
        if not items:
            diagnostics["posts_skipped"] += 1
    diagnostics["posts_parsed"] = len(posts)
    return posts


def _load_posts_modern_posts_json(posts_json_files, input_dir, diagnostics, verbose=False):
    input_dir = os.path.abspath(input_dir)
    diagnostics["format"] = "modern-posts-json"
    diagnostics["json_files_found"] = len(posts_json_files)
    posts = []
    for filename in sorted(posts_json_files):
        if verbose:
            print("Opening posts file %s" % filename)
        with open(filename, encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            diagnostics["posts_skipped"] += 1
            continue
        for post in data:
            if not post or not isinstance(post, dict):
                diagnostics["posts_skipped"] += 1
                continue
            caption = post.get("title") or ""
            ts = post.get("creation_timestamp")
            dt = datetime.fromtimestamp(ts) if ts is not None else None
            hash_key = dt.strftime("%Y-%m-%d %H:%M") if dt else "unknown"
            date_label = dt.strftime("%B %d, %Y") if dt else ""
            items = []
            for m in post.get("media") or []:
                if not isinstance(m, dict):
                    continue
                uri = m.get("uri")
                if not uri:
                    continue
                source_file = resolve_posts_export_uri(filename, uri)
                if not os.path.isfile(source_file):
                    diagnostics["media_files_missing"] += 1
                    if verbose:
                        print("ERROR: Unable to find file at %s" % source_file)
                    continue
                diagnostics["media_files_resolved"] += 1
                relative_path = os.path.relpath(source_file, input_dir).replace("\\", "/")
                items.append(
                    {
                        "media_type": "VIDEO" if relative_path.lower().endswith("mp4") else "IMAGE",
                        "media_url": relative_path,
                    }
                )
            if not items:
                continue
            posts.append(
                {
                    "caption": caption,
                    "date_label": date_label,
                    "timestamp_raw": hash_key,
                    "items": items,
                }
            )
    diagnostics["posts_parsed"] = len(posts)
    return posts


def load_posts_from_dump(input_dir, verbose=False):
    input_dir = os.path.abspath(input_dir)
    diagnostics = make_diagnostics(input_dir)
    media_files, posts_json_files = scan_dump_inputs(input_dir)

    if media_files:
        posts = _load_posts_legacy_media_json(media_files, input_dir, diagnostics, verbose=verbose)
        for post in posts:
            validate_post_schema(post)
        return posts, diagnostics
    if posts_json_files:
        posts = _load_posts_modern_posts_json(posts_json_files, input_dir, diagnostics, verbose=verbose)
        for post in posts:
            validate_post_schema(post)
        return posts, diagnostics
    fail(
        "E_NO_INPUT_JSON",
        "No media.json or posts_<n>.json found under %s." % input_dir,
        "Unzip all archive parts and pass the directory that contains your_instagram_activity.",
    )


def run(argv):
    input_dir = None
    verbose = False
    output_theme = "classic"
    output_layout = "stacked"
    doctor_mode = False
    doctor_json_mode = False
    doctor_json_format = "compact"
    strict_mode = False
    strict_max_missing_media = STRICT_DEFAULT_MAX_MISSING_MEDIA

    try:
        opts, _args = getopt.getopt(
            argv,
            "hi:v",
            [
                "inputdir=",
                "theme=",
                "layout=",
                "doctor",
                "doctor-json",
                "doctor-json-format=",
                "doctor-json-pretty",
                "strict",
                "strict-max-missing-media=",
            ],
        )
    except getopt.GetoptError as err:
        print(err)
        usage()
        sys.exit(2)

    for opt, arg in opts:
        if opt == "-h":
            usage()
            sys.exit()
        if opt in ("-i", "--inputdir"):
            input_dir = arg
        elif opt == "-v":
            verbose = True
        elif opt == "--theme":
            candidate = arg.strip().lower()
            if candidate not in OUTPUT_THEMES:
                print(
                    "Invalid --theme value '%s'. Expected one of: %s" % (arg, ", ".join(sorted(OUTPUT_THEMES.keys())))
                )
                sys.exit(2)
            output_theme = candidate
        elif opt == "--layout":
            candidate = arg.strip().lower()
            if candidate not in ("stacked", "grid"):
                print("Invalid --layout value '%s'. Expected stacked or grid" % arg)
                sys.exit(2)
            output_layout = candidate
        elif opt == "--doctor":
            doctor_mode = True
        elif opt == "--doctor-json":
            doctor_json_mode = True
            doctor_mode = True
        elif opt == "--doctor-json-format":
            candidate = arg.strip().lower()
            if candidate not in ("pretty", "compact"):
                print("Invalid --doctor-json-format value '%s'. Expected pretty or compact" % arg)
                sys.exit(2)
            doctor_json_format = candidate
            doctor_json_mode = True
            doctor_mode = True
        elif opt == "--doctor-json-pretty":
            doctor_json_format = "pretty"
            doctor_json_mode = True
            doctor_mode = True
        elif opt == "--strict":
            strict_mode = True
        elif opt == "--strict-max-missing-media":
            try:
                strict_max_missing_media = int(arg)
                if strict_max_missing_media < 0:
                    raise ValueError()
            except ValueError:
                print("Invalid --strict-max-missing-media value '%s'. Expected non-negative integer" % arg)
                sys.exit(2)

    try:
        if input_dir is None:
            fail(
                "E_ARGS_INPUT_DIR",
                "No input directory specified.",
                "Use -i <inputdir> with an extracted Instagram export.",
            )
        if not os.path.isdir(input_dir):
            fail(
                "E_INPUT_DIR_MISSING",
                "Unable to find input_dir '%s'." % input_dir,
                "Check path spelling and unzip location.",
            )

        if not doctor_json_mode:
            print("Processing data in %s" % input_dir)
        posts, diagnostics = load_posts_from_dump(input_dir, verbose=verbose)
        if doctor_json_mode:
            print_diagnostics_json(diagnostics, json_format=doctor_json_format)
        else:
            print_diagnostics(diagnostics)
        enforce_strict(diagnostics, strict_enabled=strict_mode, max_missing_media=strict_max_missing_media)
        if doctor_mode:
            if not doctor_json_mode:
                print("Doctor mode complete. Skipped HTML generation.")
            return
        write_output(
            input_dir,
            render_posts(
                posts,
                descending=True,
                layout=output_layout,
            ),
            theme=output_theme,
        )
        print("Generated output in %s" % input_dir)
    except ConverterError as err:
        print("ERROR [%s]: %s" % (err.code, err))
        if err.hint:
            print("Hint: %s" % err.hint)
        sys.exit(3)
