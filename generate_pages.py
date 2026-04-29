#!/usr/bin/env python3
"""Generate environment HTML pages from markdown files."""

import re
import shutil
from collections import defaultdict
from pathlib import Path

import markdown
import nbformat
from nbconvert import HTMLExporter
from PIL import Image

NAV_ITEMS = [
    ('about', 'About'),
    ('usage', 'Installation'),
    ('tutorials', 'Tutorials'),
    ('benchmark', 'Environments'),
    ('results', 'Results'),
    ('real-robots', 'Real Robots'),
    ('citation', 'Citation'),
    ('contact', 'Contact'),
]

NOTEBOOKS = [
    {
        'path': 'kindergarden/notebooks/getting_started.ipynb',
        'slug': 'getting-started',
        'title': 'Getting Started',
        'description': 'Walk through the basics: discovering environments, creating one, taking actions, and rendering a video.',
        'package': 'kinder',
    },
    {
        'path': 'kinder-baselines/kinder-trajopt/notebooks/model_predictive_control.ipynb',
        'slug': 'model-predictive-control',
        'title': 'Model-Predictive Control',
        'description': 'Use get_state, set_state, and get_next_state for model-based planning with random-shooting MPC.',
        'package': 'kinder-trajopt',
    },
    {
        'path': 'kinder-baselines/kinder-bilevel-planning/notebooks/bilevel_planning.ipynb',
        'slug': 'bilevel-planning',
        'title': 'Bilevel Planning',
        'description': 'Set up predicates, operators, and skills, then run a SESAME-style bilevel planner on an Obstruction2D task.',
        'package': 'kinder-bilevel-planning',
    },
]

FOOTER_TEXT = '&copy; 2026 KinDER. All rights reserved.'


def generate_header(prefix='', title='KinDER', floating=False):
    """Generate the site header HTML.

    prefix: path prefix for links ('' for index.html, '../' for depth=1, etc.)
    title: the h1 title text
    floating: if True, render a hero-merged floating nav (hidden until scroll)
    """
    if prefix:
        nav_links = '\n'.join(
            f'                    <li><a href="{prefix}index.html#{id}">{label}</a></li>'
            for id, label in NAV_ITEMS
        )
        title_html = f'<a href="{prefix}index.html" style="color: white; text-decoration: none;">{title}</a>'
    else:
        nav_links = '\n'.join(
            f'                    <li><a href="#{id}">{label}</a></li>'
            for id, label in NAV_ITEMS
        )
        # On index, link the wordmark back to the top of the page.
        title_html = f'<a href="#top" style="color: white; text-decoration: none;">{title}</a>'

    header_class = ' class="header-floating"' if floating else ''

    return f'''    <header{header_class}>
        <nav>
            <div class="container">
                <h1>{title_html}</h1>
                <ul class="nav-links">
{nav_links}
                </ul>
            </div>
        </nav>
    </header>'''


def generate_footer():
    """Generate the site footer HTML."""
    return f'''    <footer>
        <div class="container">
            <p>{FOOTER_TEXT}</p>
        </div>
    </footer>'''


def base_template(title, breadcrumb_html, content_html, depth=1):
    """Generate a complete HTML page with consistent header/footer.

    depth=1: environments/*.html (category pages)
    depth=2: environments/<group>/*.html (group and variant pages)
    """
    prefix = '../' * depth
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | KinDER</title>
    <link rel="stylesheet" href="{prefix}styles.css">
    <link rel="stylesheet" href="{prefix}environments/environment.css">
</head>
<body>
{generate_header(prefix, 'KinDER')}
    <main>
        <section class="environment-detail">
            <div class="container">
                <div class="breadcrumb">{breadcrumb_html}</div>
{content_html}
                <div class="back-link">
                    <a href="{prefix}index.html#benchmark">← Back to Benchmark</a>
                </div>
            </div>
        </section>
    </main>
{generate_footer()}
</body>
</html>
"""


def slugify(name):
    """Convert a name to a URL-safe slug."""
    return re.sub(r'[-\s]+', '-', re.sub(r'[^\w\s-]', '', name.lower()))


def extract_base_name(env_name):
    """Extract base environment name without variant suffixes."""
    name = re.sub(r'-v\d+$', '', env_name)

    for prefix in ('TidyBot3D', 'RBY1A3D'):
        if name.startswith(prefix):
            parts = name.split('-')
            if len(parts) >= 3 and re.match(r'^[a-z]\d+$', parts[-1]):
                return '-'.join(parts[:-1])

    parts = name.split('-')
    if len(parts) >= 2 and re.match(r'^[a-z]\d+$', parts[-1]):
        return '-'.join(parts[:-1])
    return name


def categorize_environment(env_name):
    """Determine category based on environment name."""
    name_lower = env_name.lower()
    is_3d = '3d' in name_lower

    if is_3d:
        is_dynamic = 'tidybot' in name_lower or 'rby1a' in name_lower
        return "Dynamic 3D" if is_dynamic else "Kinematic 3D"
    else:
        is_dynamic = name_lower.startswith('dyn')
        return "Dynamic 2D" if is_dynamic else "Kinematic 2D"


def extract_first_frame_as_png(gif_path, png_path, crop_square=False):
    """Extract the first frame of a GIF and save as PNG.

    If crop_square=True, crop to a centered square.
    """
    try:
        with Image.open(gif_path) as img:
            img.seek(0)
            frame = img.convert('RGBA')

            if crop_square:
                width, height = frame.size
                size = min(width, height)
                left = (width - size) // 2
                top = (height - size) // 2
                frame = frame.crop((left, top, left + size, top + size))

            frame.save(png_path, 'PNG')
            return True
    except Exception as e:
        print(f"  Warning: Could not extract PNG from {gif_path}: {e}")
        return False


def generate_gif_grid_html(gifs):
    """Generate HTML for a grid of GIFs.

    gifs: dict with keys 'initial', 'random', 'demo' mapping to GIF paths
    """
    if not gifs:
        return ''

    gif_config = [
        ('initial', 'Initial State Distribution'),
        ('random', 'Random Action Behavior'),
        ('demo', 'Example Demonstration'),
    ]

    items = []
    for key, label in gif_config:
        if key in gifs:
            items.append(
                f'                        <div class="gif-container">\n'
                f'                            <h3>{label}</h3>\n'
                f'                            <img src="{gifs[key]}" alt="{label}">\n'
                f'                        </div>'
            )

    if not items:
        return ''
    return f'                    <div class="gifs-grid">\n' + '\n'.join(items) + '\n                    </div>\n\n'


def get_hero_gif_path(group_name, assets_dir):
    """Get the hero GIF path for a group from group_gifs directory."""
    gif_path = assets_dir / 'group_gifs' / f'{group_name}.gif'
    if gif_path.exists():
        return gif_path
    return None


def extract_gifs_from_markdown(content, depth=2):
    """Extract GIF paths from markdown content for Initial State, Random Action, and Demo."""
    prefix = '../' * depth
    gifs = {}

    # Extract Initial State Distribution GIF
    init_match = re.search(r'## Initial State Distribution\s*\n!\[.*?\]\((\.\.\/\.\.\/assets/[^\)]+\.gif)\)', content)
    if init_match:
        gifs['initial'] = init_match.group(1).replace('../../assets/', f'{prefix}kindergarden/docs/envs/assets/')

    # Extract Random Action Behavior GIF
    random_match = re.search(r'## Random Action Behavior\s*\n!\[.*?\]\((\.\.\/\.\.\/assets/[^\)]+\.gif)\)', content)
    if random_match:
        gifs['random'] = random_match.group(1).replace('../../assets/', f'{prefix}kindergarden/docs/envs/assets/')

    # Extract Example Demonstration GIF
    demo_match = re.search(r'## Example Demonstration\s*\n!\[.*?\]\((\.\.\/\.\.\/assets/[^\)]+\.gif)\)', content)
    if demo_match:
        gifs['demo'] = demo_match.group(1).replace('../../assets/', f'{prefix}kindergarden/docs/envs/assets/')

    return gifs


def extract_section(content, section_name):
    """Extract a section's content from markdown using ## headers."""
    match = re.search(rf'^## {section_name}\s*\n(.*?)(?=\n## |\Z)', content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ''


def has_demo_gif(content):
    """Check if content has a demonstration GIF."""
    return bool(re.search(r'## Example Demonstration\s*\n!\[.*?\]\(assets/.*?\.gif\)', content))


def parse_group_file(md_path, assets_dir):
    """Parse a group markdown file and return structured data."""
    content = md_path.read_text(encoding='utf-8')
    name_match = re.search(r'^# (.+)$', content, re.MULTILINE)
    group_name = name_match.group(1).strip() if name_match else "Unknown"

    hero_gif = get_hero_gif_path(group_name, assets_dir)

    return {
        'name': group_name,
        'content': content,
        'hero_gif': hero_gif,
        'description': extract_section(content, 'Description'),
        'references': extract_section(content, 'References'),
        'action_space': extract_section(content, 'Action Space'),
        'rewards': extract_section(content, 'Rewards'),
        'has_demo': hero_gif is not None,
        'md_path': md_path,
    }


def parse_variant_file(md_path, group_name):
    """Parse a variant markdown file and return structured data."""
    content = md_path.read_text(encoding='utf-8')
    name_match = re.search(r'^# (.+)$', content, re.MULTILINE)
    variant_name = name_match.group(1).strip() if name_match else "Unknown"

    return {
        'name': variant_name,
        'content': content,
        'gifs': extract_gifs_from_markdown(content, depth=2),
        'description': extract_section(content, 'Description'),
        'usage': extract_section(content, 'Usage'),
        'observation_space': extract_section(content, 'Observation Space'),
        'has_demo': has_demo_gif(content),
        'md_path': md_path,
        'group_name': group_name,
    }


def filter_markdown_for_html(content, depth=2):
    """Remove GIF sections, fix paths, and ensure tables have blank lines."""
    lines = content.split('\n')
    filtered = []
    skip = False

    # Sections to skip (they're displayed in the GIF grid instead)
    skip_sections = (
        '## Initial State Distribution',
        '## Random Action Behavior',
        '## Example Demonstration',
    )

    for line in lines:
        if 'random_action_gifs' in line:
            continue
        if line.strip() in skip_sections:
            skip = True
            continue
        if skip and line.strip().startswith('## '):
            skip = False
        if skip:
            continue
        filtered.append(line)

    processed = []
    in_table = False
    for line in filtered:
        is_table_line = line.strip().startswith('|') and line.strip().endswith('|')
        if is_table_line and not in_table:
            if processed and processed[-1].strip():
                processed.append('')
            in_table = True
        elif not is_table_line and in_table:
            in_table = False
            if line.strip():
                processed.append('')
        processed.append(line)

    prefix = '../' * depth
    result = '\n'.join(processed)
    # Handle both direct assets/ paths and relative ../../assets/ paths from variant files
    result = result.replace('](../../assets/', f']({prefix}kindergarden/docs/envs/assets/')
    result = result.replace('](assets/', f']({prefix}kindergarden/docs/envs/assets/')
    result = result.replace('="../../assets/', f'="{prefix}kindergarden/docs/envs/assets/')
    result = result.replace('="assets/', f'="{prefix}kindergarden/docs/envs/assets/')
    return result


def preprocess_markdown(content):
    """Preprocess markdown to fix common issues before conversion.

    - Ensures blank lines before lists (required by Python-Markdown)
    - Ensures blank lines before headers
    """
    lines = content.split('\n')
    result = []
    for i, line in enumerate(lines):
        # Check if this line starts a list or header and previous line is non-empty
        is_list_start = line.strip().startswith(('- ', '* ', '+ ')) or re.match(r'^\d+\. ', line.strip())
        is_header = line.strip().startswith('#')
        prev_non_empty = i > 0 and result and result[-1].strip()

        if (is_list_start or is_header) and prev_non_empty:
            result.append('')
        result.append(line)
    return '\n'.join(result)


def convert_markdown_to_html(md_content):
    """Convert markdown content to HTML."""
    preprocessed = preprocess_markdown(md_content)
    md = markdown.Markdown(extensions=['tables', 'fenced_code'])
    return md.convert(preprocessed)


def create_environment_page(variant_data, group_data, category):
    """Create an HTML page for a single environment variant."""
    prefix = '../../'
    cat_slug = slugify(category)
    group_name = variant_data['group_name']
    group_slug = slugify(group_name)

    breadcrumb = (f'<a href="{prefix}index.html#benchmark">Benchmark</a> / '
                  f'<a href="{prefix}environments/{cat_slug}.html">{category}</a> / '
                  f'<a href="{prefix}environments/{group_slug}/index.html">{group_name}</a> / '
                  f'<span>{variant_data["name"]}</span>')

    filtered = filter_markdown_for_html(variant_data['content'], depth=2)
    html_content = convert_markdown_to_html(filtered)

    title_match = re.search(r'<h1>(.*?)</h1>', html_content)
    title_html = f'<h1>{title_match.group(1)}</h1>\n' if title_match else ''
    html_content = re.sub(r'<h1>.*?</h1>\n?', '', html_content, count=1)

    content = f'''
                <div class="environment-content">
                    {title_html}{generate_gif_grid_html(variant_data['gifs'])}{html_content}
                </div>
'''
    return base_template(variant_data['name'], breadcrumb, content, depth=2)


def generate_hero_gif_html(hero_gif_url):
    """Generate HTML for the hero GIF display."""
    if not hero_gif_url:
        return ''
    return f'''                    <div class="hero-gif">
                        <img src="{hero_gif_url}" alt="Environment demonstration">
                    </div>

'''


def create_group_page(group_data, category, variants):
    """Create an HTML page for an environment group (index.html in group folder)."""
    prefix = '../../'
    cat_slug = slugify(category)
    group_name = group_data['name']

    breadcrumb = (f'<a href="{prefix}index.html#benchmark">Benchmark</a> / '
                  f'<a href="{prefix}environments/{cat_slug}.html">{category}</a> / '
                  f'<span>{group_name}</span>')

    desc = group_data.get('description', '')
    desc_html = convert_markdown_to_html(desc) if desc else '<p>No description available.</p>'
    refs = group_data.get('references', '')
    refs_html = convert_markdown_to_html(refs) if refs else '<p>No references available.</p>'

    hero_gif_url = group_data.get('hero_gif_url', '')
    hero_html = generate_hero_gif_html(hero_gif_url)

    variants_html = '\n'.join(
        f'''                        <div class="variant-card">
                            <a href="{slugify(v['name'])}.html" class="variant-link">
                                <h3>{v['name']}</h3>
                                <p class="variant-description">{v.get('description', 'View details →')[:100]}</p>
                            </a>
                        </div>'''
        for v in sorted(variants, key=lambda x: x['name'])
    )

    content = f'''
                <h1>{group_name}</h1>

                <div class="environment-content">
{hero_html}                    <h2>Description</h2>
                    {desc_html}

                    <h2>Variants</h2>
                    <p>This environment has {len(variants)} variant(s).</p>

                    <div class="variant-list">
{variants_html}
                    </div>

                    <h2>References</h2>
                    {refs_html}
                </div>
'''
    return base_template(group_name, breadcrumb, content, depth=2)


def create_category_page(category_name, families):
    """Create an HTML page for a category."""
    prefix = '../'
    breadcrumb = f'<a href="{prefix}index.html#benchmark">Benchmark</a> / <span>{category_name}</span>'

    families_html = '\n'.join(
        f'''                        <div class="family-card">
                            <a href="{slugify(f['base_name'])}/index.html" class="family-link">
                                <h3>{f['base_name']}</h3>
                                <p class="family-meta">{f['count']} variant{"s" if f['count'] != 1 else ""}</p>
                            </a>
                        </div>'''
        for f in sorted(families, key=lambda x: x['base_name'])
    )

    content = f'''
                <h1>{category_name}</h1>

                <div class="environment-content">
                    <h2>Environment Families</h2>

                    <div class="env-families-list">
{families_html}
                    </div>
                </div>
'''
    return base_template(category_name, breadcrumb, content, depth=1)


def generate_results_section_html():
    """Generate the results section HTML with figure."""
    return '''        <section id="results">
            <div class="container">
                <h2>KinDERBench: Benchmark and Results</h2>
                <p>See the plot below for a summary of our main empirical results. See paper for details and additional results with additional metrics.</p>
                <img src="assets/figure1_bar_v4.png" alt="Benchmark results" class="results-figure">
                <p>Success rates: mean ± std across 5 seeds and 50 episodes per seed.</p>
            </div>
        </section>'''


def generate_hero_section_html(groups):
    """Generate the hero section HTML with GIF grid for index.html."""
    items = []
    for group_name in sorted(groups.keys()):
        group_info = groups[group_name]
        group_data = group_info['data']
        if not group_data.get('hero_gif'):
            continue
        slug = slugify(group_name)
        gif_path = f'kindergarden/docs/envs/assets/group_gifs/{group_name}.gif'
        png_path = f'environments/thumbnails/{group_name}.png'
        items.append(
            f'                        <a href="environments/{slug}/index.html" class="demo-gif-item" '
            f'data-gif="{gif_path}" data-static="{png_path}">\n'
            f'                            <img src="{png_path}" alt="{group_name} Demo">\n'
            f'                            <span class="demo-label">{group_name}</span>\n'
            f'                        </a>'
        )

    if not items:
        return ''

    return f'''        <section id="hero">
            <div class="container">
                <p class="hover-instruction">Hover over the environments below to see them in action</p>
                <div class="demo-showcase">
                    <div class="demo-gif-grid">
{chr(10).join(items)}
                    </div>
                </div>
            </div>
        </section>'''


def generate_index_category_html(category_name, groups):
    """Generate HTML for a category card in index.html."""
    items = []
    for base_name, variants in sorted(groups.items()):
        count = len(variants)
        link = f"environments/{slugify(base_name)}/index.html"
        items.append(f'                            <li><a href="{link}">{base_name}</a> '
                     f'<span class="env-count">{count} variant{"s" if count != 1 else ""}</span></li>')

    return f'''
                    <div class="env-category-card">
                        <h3><a href="environments/{slugify(category_name)}.html">{category_name}</a></h3>
                        <ul class="env-list">
{chr(10).join(items)}
                        </ul>
                    </div>
'''


def preprocess_notebook_gif_outputs(nb):
    """Convert image/gif outputs to HTML so nbconvert renders them."""
    for cell in nb.cells:
        if cell.cell_type != 'code':
            continue
        for output in cell.get('outputs', []):
            data = output.get('data', {})
            if 'image/gif' not in data:
                continue
            gif_b64 = data['image/gif']
            if isinstance(gif_b64, list):
                gif_b64 = ''.join(gif_b64)
            html = f'<img src="data:image/gif;base64,{gif_b64}" alt="Output">'
            data['text/html'] = html
            del data['image/gif']
            if 'text/plain' in data:
                del data['text/plain']


def notebook_to_html(notebook_path):
    """Convert a Jupyter notebook to an HTML body fragment.

    Returns the HTML content of the notebook cells (no full page wrapper)
    and the Pygments CSS needed for syntax highlighting.
    """
    nb = nbformat.read(notebook_path, as_version=4)
    preprocess_notebook_gif_outputs(nb)
    exporter = HTMLExporter()
    exporter.template_name = 'basic'
    exporter.exclude_input_prompt = True
    exporter.exclude_output_prompt = True
    full_html, _resources = exporter.from_notebook_node(nb)

    # Extract body content (drop the html/head/body wrapper)
    body_match = re.search(r'<body[^>]*>(.*)</body>', full_html, re.DOTALL)
    body = body_match.group(1).strip() if body_match else full_html

    # Extract the Pygments syntax highlighting CSS (first <style> block)
    pygments_css = ''
    style_match = re.search(r'<style[^>]*>(.*?)</style>', full_html, re.DOTALL)
    if style_match:
        pygments_css = style_match.group(1)

    # Remove anchor-link pilcrows that nbconvert adds to headings
    body = re.sub(r'<a class="anchor-link" href="[^"]*">.*?</a>', '', body)

    return body, pygments_css


def create_notebook_page(nb_config, body_html, pygments_css):
    """Create an HTML page for a single notebook tutorial."""
    prefix = '../'
    breadcrumb = (f'<a href="{prefix}index.html#tutorials">Tutorials</a> / '
                  f'<span>{nb_config["title"]}</span>')

    content = f'''
                <div class="notebook-content">
                    <div class="notebook-toolbar">
                        <a href="{nb_config['slug']}.ipynb" download class="notebook-download">Download notebook (.ipynb)</a>
                    </div>
                    {body_html}
                </div>
'''
    # Build page with pygments CSS included
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{nb_config['title']} | KinDER Tutorials</title>
    <link rel="stylesheet" href="{prefix}styles.css">
    <link rel="stylesheet" href="{prefix}environments/environment.css">
    <link rel="stylesheet" href="{prefix}tutorials/notebook.css">
    <style>{pygments_css}</style>
</head>
<body class="notebook-page">
{generate_header(prefix, 'KinDER')}
    <main>
        <section class="environment-detail">
            <div class="container">
                <div class="breadcrumb">{breadcrumb}</div>
{content}
                <div class="back-link">
                    <a href="{prefix}index.html#tutorials">&larr; Back to Tutorials</a>
                </div>
            </div>
        </section>
    </main>
{generate_footer()}
</body>
</html>
"""


def generate_tutorials_section_html(notebooks):
    """Generate the tutorials section HTML for index.html."""
    cards = []
    for nb in notebooks:
        cards.append(f'''                    <div class="tutorial-card">
                        <a href="tutorials/{nb['slug']}.html" class="tutorial-link">
                            <span class="tutorial-package">{nb['package']}</span>
                            <h3>{nb['title']}</h3>
                            <p>{nb['description']}</p>
                        </a>
                    </div>''')

    return f'''        <section id="tutorials">
            <div class="container">
                <h2>Tutorials</h2>
                <p>Step-by-step tutorials for getting started with KinDER.</p>

                <div class="tutorials-grid">
{chr(10).join(cards)}
                </div>
            </div>
        </section>'''


def load_whitelist(path):
    """Load environment whitelist from file with category assignments.

    Returns a dict mapping environment name to category.
    Categories are specified by comment lines starting with #.
    """
    whitelist_path = Path(path)
    if not whitelist_path.exists():
        return None

    env_to_category = {}
    current_category = None

    for line in whitelist_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            current_category = line[1:].strip()
        elif current_category:
            env_to_category[line] = current_category

    return env_to_category


def main():
    print("KinDER Environment Page Generator")
    print("=" * 60)

    md_dir = Path('kindergarden/docs/envs')
    assets_dir = md_dir / 'assets'
    if not md_dir.exists():
        print("Error: kindergarden/docs/envs/ directory not found!")
        return

    # Load whitelist
    whitelist = load_whitelist('env_whitelist.txt')
    if whitelist:
        print(f"Loaded whitelist with {len(whitelist)} environments")
    else:
        print("No whitelist found, including all environments")

    # Parse group files from root of envs directory
    group_files = [f for f in md_dir.glob('*.md') if f.name.lower() != 'readme.md']
    print(f"Found {len(group_files)} group files")

    groups = {}
    for group_file in group_files:
        group_data = parse_group_file(group_file, assets_dir)
        group_name = group_data['name']
        # Skip groups not in whitelist
        if whitelist and group_name not in whitelist:
            continue
        # Use category from whitelist, fall back to auto-detection
        group_data['category'] = whitelist.get(group_name) if whitelist else categorize_environment(group_name)
        groups[group_name] = {
            'data': group_data,
            'variants': []
        }

    print(f"Including {len(groups)} groups (after whitelist filtering)")

    # Parse variant files from variants subdirectories
    variants_dir = md_dir / 'variants'
    variant_count = 0
    for group_name in groups:
        group_variant_dir = variants_dir / group_name
        if group_variant_dir.exists():
            for variant_file in group_variant_dir.glob('*.md'):
                variant_data = parse_variant_file(variant_file, group_name)
                variant_data['category'] = groups[group_name]['data']['category']
                groups[group_name]['variants'].append(variant_data)
                variant_count += 1

    print(f"Found {variant_count} variant files across {len(groups)} groups")

    # Build categories structure
    categories = defaultdict(lambda: defaultdict(list))
    for group_name, group_info in groups.items():
        category = group_info['data']['category']
        categories[category][group_name] = group_info['variants']

    out_dir = Path('environments')

    # Clean up old flat HTML files (but keep environment.css and subdirectories we'll create)
    print("\nCleaning up old files...")
    for old_file in out_dir.glob('*.html'):
        old_file.unlink()
    for old_dir in out_dir.iterdir():
        if old_dir.is_dir():
            shutil.rmtree(old_dir)

    # Generate static PNGs from hero GIFs
    print("\nGenerating static thumbnails from GIFs...")
    thumbnails_dir = out_dir / 'thumbnails'
    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    png_count = 0
    for group_name, group_info in groups.items():
        group_data = group_info['data']
        hero_gif = group_data.get('hero_gif')
        if hero_gif and hero_gif.exists():
            png_path = thumbnails_dir / f'{group_name}.png'
            # Crop Dynamic 3D thumbnails to square
            crop_square = group_data.get('category') == 'Dynamic 3D'
            if extract_first_frame_as_png(hero_gif, png_path, crop_square=crop_square):
                png_count += 1
            # Set URLs for use in templates (relative to group page at depth=2)
            group_data['hero_gif_url'] = f'../../kindergarden/docs/envs/assets/group_gifs/{group_name}.gif'
            group_data['thumbnail_url'] = f'../thumbnails/{group_name}.png'
        else:
            group_data['hero_gif_url'] = ''
            group_data['thumbnail_url'] = ''
    print(f"  Generated {png_count} PNG thumbnails")

    # Generate group directories with variant pages and index.html
    print("\nGenerating environment pages...")
    for group_name, group_info in groups.items():
        group_data = group_info['data']
        variants = group_info['variants']
        category = group_data['category']

        group_dir = out_dir / slugify(group_name)
        group_dir.mkdir(parents=True, exist_ok=True)

        # Generate variant pages
        for variant in variants:
            html = create_environment_page(variant, group_data, category)
            (group_dir / f"{slugify(variant['name'])}.html").write_text(html, encoding='utf-8')

        # Generate group index page
        html = create_group_page(group_data, category, variants)
        (group_dir / 'index.html').write_text(html, encoding='utf-8')

    print(f"  Generated {variant_count} variant pages in {len(groups)} group directories")

    # Generate category pages
    print("\nGenerating category pages...")
    for cat_name in ['Kinematic 2D', 'Kinematic 3D', 'Dynamic 2D', 'Dynamic 3D']:
        if cat_name in categories:
            families = [{'base_name': bn, 'count': len(vs)} for bn, vs in categories[cat_name].items()]
            html = create_category_page(cat_name, families)
            (out_dir / f"{slugify(cat_name)}.html").write_text(html, encoding='utf-8')
    print(f"  Generated {len(categories)} category pages")

    # Generate tutorial pages from notebooks
    print("\nGenerating tutorial pages...")
    tutorials_dir = Path('tutorials')
    tutorials_dir.mkdir(parents=True, exist_ok=True)
    for old_file in tutorials_dir.glob('*.html'):
        old_file.unlink()
    for nb_config in NOTEBOOKS:
        nb_path = Path(nb_config['path'])
        if not nb_path.exists():
            print(f"  Warning: {nb_path} not found, skipping")
            continue
        body_html, pygments_css = notebook_to_html(nb_path)
        html = create_notebook_page(nb_config, body_html, pygments_css)
        (tutorials_dir / f"{nb_config['slug']}.html").write_text(html, encoding='utf-8')
        # Copy the .ipynb file so it can be downloaded
        shutil.copy2(nb_path, tutorials_dir / f"{nb_config['slug']}.ipynb")
        print(f"  Generated {nb_config['slug']}.html")

    # Generate index.html from template
    print("\nGenerating index.html from template...")
    template_path = Path('index_template.html')
    index_path = Path('index.html')
    if template_path.exists():
        content = template_path.read_text(encoding='utf-8')

        # Replace header and footer. On the index, the full title lives in
        # the hero section, so the floating nav uses the short wordmark.
        content = content.replace('{{HEADER}}', generate_header(
            prefix='',
            title='KinDER',
            floating=True,
        ))
        content = content.replace('{{FOOTER}}', generate_footer())

        # Replace hero section
        hero_html = generate_hero_section_html(groups)
        content = content.replace('{{HERO_SECTION}}', hero_html)

        benchmark_html = '''        <section id="benchmark">
            <div class="container">
                <h2>KinDERGarden: Environments</h2>
                <p>KinDER environments are organized into four categories.</p>

                <div class="env-categories-grid">
'''
        for cat_name in ['Kinematic 2D', 'Kinematic 3D', 'Dynamic 2D', 'Dynamic 3D']:
            if cat_name in categories:
                benchmark_html += generate_index_category_html(cat_name, categories[cat_name])
        benchmark_html += '''                </div>
            </div>
        </section>'''

        content = content.replace('{{BENCHMARK_SECTION}}', benchmark_html)

        tutorials_html = generate_tutorials_section_html(NOTEBOOKS)
        content = content.replace('{{TUTORIALS_SECTION}}', tutorials_html)

        results_html = generate_results_section_html()
        content = content.replace('{{RESULTS_SECTION}}', results_html)

        index_path.write_text(content, encoding='utf-8')
        print("  Generated index.html")
    else:
        print("  Warning: index_template.html not found!")

    print("\n" + "=" * 60)
    print("Summary:")
    for cat, cat_groups in categories.items():
        print(f"  {cat}: {sum(len(v) for v in cat_groups.values())} environments in {len(cat_groups)} families")
    print("=" * 60)
    print(f"\n✓ Generated {variant_count} pages successfully!")


if __name__ == '__main__':
    main()
