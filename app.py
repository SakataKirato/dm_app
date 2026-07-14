#!/usr/keio/Anaconda3-2025.12-2/bin/python
"""AI モデル・リーダーボード検索アプリケーション。"""

import sqlite3
from pathlib import Path
from typing import Optional

from flask import Flask, abort, g, jsonify, render_template, request


DATABASE = Path(__file__).with_name('leaderboard.db')
PAGE_SIZE = 50
app = Flask(__name__)


def get_db() -> sqlite3.Connection:
    """リクエスト中で共有する SQLite 接続を取得する。"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception: Optional[BaseException]) -> None:
    """リクエスト終了時にデータベース接続を閉じる。"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def fetch_filter_options(
    arena_id: int | None = None, category: str = ''
) -> dict[str, object]:
    """ランキング画面の絞り込み候補を取得する。"""
    db = get_db()
    category_rows = db.execute(
        'SELECT arena_id, category FROM leaderboard_results '
        'GROUP BY arena_id, category '
        "ORDER BY arena_id, CASE WHEN category = 'overall' THEN 0 ELSE 1 END, category"
    ).fetchall()
    categories_by_arena: dict[int, list[str]] = {}
    for row in category_rows:
        categories_by_arena.setdefault(row['arena_id'], []).append(row['category'])

    date_rows = db.execute(
        'SELECT arena_id, category, leaderboard_publish_date '
        'FROM leaderboard_results '
        'GROUP BY arena_id, category, leaderboard_publish_date '
        'ORDER BY arena_id, category, leaderboard_publish_date DESC'
    ).fetchall()
    dates_by_arena_category: dict[int, dict[str, list[str]]] = {}
    for row in date_rows:
        dates_by_arena_category.setdefault(row['arena_id'], {}).setdefault(
            row['category'], []
        ).append(row['leaderboard_publish_date'])

    category_query = 'SELECT DISTINCT category FROM leaderboard_results'
    category_params: tuple[object, ...] = ()
    if arena_id is not None:
        category_query += ' WHERE arena_id = ?'
        category_params = (arena_id,)
    category_query += " ORDER BY CASE WHEN category = 'overall' THEN 0 ELSE 1 END, category"
    date_query = 'SELECT DISTINCT leaderboard_publish_date FROM leaderboard_results'
    date_params: tuple[object, ...] = ()
    if arena_id is not None and category:
        date_query += ' WHERE arena_id = ? AND category = ?'
        date_params = (arena_id, category)
    date_query += ' ORDER BY leaderboard_publish_date DESC'
    arenas = db.execute('SELECT * FROM arenas ORDER BY arena_name').fetchall()
    return {
        'arenas': arenas,
        'arena_menu': [
            {'id': row['arena_id'], 'name': row['arena_name']} for row in arenas
        ],
        'organizations': db.execute(
            'SELECT * FROM organizations ORDER BY organization_name'
        ).fetchall(),
        'licenses': db.execute('SELECT * FROM licenses ORDER BY license_name').fetchall(),
        'categories': db.execute(category_query, category_params).fetchall(),
        'categories_by_arena': categories_by_arena,
        'dates_by_arena_category': dates_by_arena_category,
        'dates': db.execute(date_query, date_params).fetchall(),
    }


def apply_default_leaderboard_filters(filters: dict[str, object]) -> None:
    """評価対象・カテゴリ・公開日を常に実在する組み合わせへ正規化する。"""
    db = get_db()
    arena = None
    if filters['arena']:
        arena = db.execute(
            'SELECT arena_id FROM arenas WHERE arena_id = ?', (filters['arena'],)
        ).fetchone()
    if arena is None:
        arena = db.execute(
            'SELECT arena_id FROM arenas WHERE arena_name = ?', ('text',)
        ).fetchone()
    if arena is None:
        arena = db.execute(
            'SELECT arena_id FROM arenas ORDER BY arena_name LIMIT 1'
        ).fetchone()
    filters['arena'] = arena['arena_id']

    category = db.execute(
        'SELECT category FROM leaderboard_results '
        'WHERE arena_id = ? AND category = ? LIMIT 1',
        (filters['arena'], filters['category']),
    ).fetchone() if filters['category'] else None
    if category is None:
        category = db.execute(
            'SELECT DISTINCT category FROM leaderboard_results '
            'WHERE arena_id = ? AND category = ? LIMIT 1',
            (filters['arena'], 'overall'),
        ).fetchone()
    if category is None:
        category = db.execute(
            'SELECT DISTINCT category FROM leaderboard_results '
            'WHERE arena_id = ? ORDER BY category LIMIT 1',
            (filters['arena'],),
        ).fetchone()
    filters['category'] = category['category']

    date = db.execute(
        'SELECT leaderboard_publish_date FROM leaderboard_results '
        'WHERE arena_id = ? AND category = ? AND leaderboard_publish_date = ? '
        'LIMIT 1',
        (filters['arena'], filters['category'], filters['date']),
    ).fetchone() if filters['date'] else None
    if date is None:
        date = db.execute(
            'SELECT DISTINCT leaderboard_publish_date FROM leaderboard_results '
            'WHERE arena_id = ? AND category = ? '
            'ORDER BY leaderboard_publish_date DESC LIMIT 1',
            (filters['arena'], filters['category']),
        ).fetchone()
    filters['date'] = date['leaderboard_publish_date']


def pagination_links(current_page: int, total_pages: int) -> list[int | None]:
    """先頭・末尾と現在ページ付近を残したページ番号列を返す。"""
    pages = {1, total_pages}
    pages.update(range(max(1, current_page - 2), min(total_pages, current_page + 2) + 1))
    links: list[int | None] = []
    for page in sorted(pages):
        if links and links[-1] is not None and page > links[-1] + 1:
            links.append(None)
        links.append(page)
    return links


def leaderboard_context() -> dict[str, object]:
    """ランキング一覧と、その表示に必要な値を取得する。"""
    keyword = request.args.get('q', default='', type=str).strip()
    sort = request.args.get('sort', default='rating', type=str)
    direction = request.args.get('direction', default='desc', type=str)
    if sort not in {'rank', 'rating', 'vote_count'}:
        sort = 'rating'
    if direction not in {'asc', 'desc'}:
        direction = 'desc'
    filters = {
        'arena': request.args.get('arena', type=int),
        'organization': request.args.get('organization', type=int),
        'license': request.args.get('license', type=int),
        'category': request.args.get('category', default='', type=str).strip(),
        'date': request.args.get('date', default='', type=str).strip(),
        'q': keyword,
        'sort': sort,
        'direction': direction,
    }
    apply_default_leaderboard_filters(filters)
    db = get_db()
    clauses: list[str] = []
    params: list[object] = []
    column_map = {
        'arena': 'a.arena_id',
        'organization': 'o.organization_id',
        'license': 'l.license_id',
        'category': 'r.category',
        'date': 'r.leaderboard_publish_date',
    }
    for key, column in column_map.items():
        value = filters[key]
        if value:
            clauses.append(f'{column} = ?')
            params.append(value)
    if filters['q']:
        clauses.append('m.model_name LIKE ?')
        keyword = f"%{filters['q']}%"
        params.append(keyword)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    total_records = db.execute(
        'SELECT COUNT(*) FROM leaderboard_results r '
        'JOIN models m ON r.model_id = m.model_id '
        'JOIN organizations o ON m.organization_id = o.organization_id '
        'JOIN licenses l ON m.license_id = l.license_id '
        'JOIN arenas a ON r.arena_id = a.arena_id '
        f'{where}', params
    ).fetchone()[0]
    total_pages = max(1, (total_records + PAGE_SIZE - 1) // PAGE_SIZE)
    current_page = max(1, request.args.get('page', default=1, type=int) or 1)
    current_page = min(current_page, total_pages)
    offset = (current_page - 1) * PAGE_SIZE
    order_by = {
        'rank': 'r.rank ASC, r.rating DESC',
        'rating': f'r.rating {direction.upper()}, r.rank ASC',
        'vote_count': (
            f'r.vote_count IS NULL ASC, r.vote_count {direction.upper()}, r.rank ASC'
        ),
    }[sort]
    results = db.execute(
        'WITH leaderboard_scope AS ('
        'SELECT model_id, rating_lower, rating_upper '
        'FROM leaderboard_results '
        'WHERE arena_id = ? AND category = ? AND leaderboard_publish_date = ?'
        '), rank_spreads AS ('
        'SELECT target.model_id, '
        '1 + COUNT(CASE WHEN other_model.rating_lower > target.rating_upper THEN 1 END) '
        'AS best_rank, '
        '1 + COUNT(CASE WHEN other_model.rating_upper > target.rating_lower THEN 1 END) '
        'AS worst_rank '
        'FROM leaderboard_scope target CROSS JOIN leaderboard_scope other_model '
        'WHERE target.rating_lower IS NOT NULL AND target.rating_upper IS NOT NULL '
        'GROUP BY target.model_id'
        ') '
        'SELECT r.result_id, r.model_id, r.rank, spread.best_rank, spread.worst_rank, '
        'r.rating, r.rating_lower, '
        'r.rating_upper, r.vote_count, m.model_name, '
        'o.organization_id, o.organization_name, l.license_id, l.license_name, '
        'a.arena_name, r.category, '
        'r.leaderboard_publish_date '
        'FROM leaderboard_results r '
        'JOIN models m ON r.model_id = m.model_id '
        'JOIN organizations o ON m.organization_id = o.organization_id '
        'JOIN licenses l ON m.license_id = l.license_id '
        'JOIN arenas a ON r.arena_id = a.arena_id '
        'LEFT JOIN rank_spreads spread ON spread.model_id = r.model_id '
        f'{where} ORDER BY {order_by} LIMIT ? OFFSET ?',
        [filters['arena'], filters['category'], filters['date'], *params, PAGE_SIZE, offset]
    ).fetchall()
    active_filters = {key: value for key, value in filters.items() if value}
    sort_filters = {
        key: value for key, value in active_filters.items()
        if key not in {'sort', 'direction'}
    }
    # 未選択時は降順の矢印を表示し、最初のクリックでは昇順にする。
    # 同じ列を続けて押した場合だけ、現在の向きと反対に切り替える。
    sort_directions = {
        column: (
            'asc' if sort != column
            else ('asc' if direction == 'desc' else 'desc')
        )
        for column in ('rating', 'vote_count')
    }
    return {
        'results': results,
        'filters': filters,
        'filter_options': fetch_filter_options(filters['arena'], filters['category']),
        'total_records': total_records,
        'current_page': current_page,
        'total_pages': total_pages,
        'page_links': pagination_links(current_page, total_pages),
        'active_filters': active_filters,
        'sort_filters': sort_filters,
        'sort_directions': sort_directions,
    }


@app.route('/')
def index() -> str:
    """絞り込み可能なランキング一覧を表示する。"""
    return render_template('index.html', **leaderboard_context())


@app.route('/api/leaderboard')
def leaderboard_api():
    """画面を再読み込みせずに一覧部分を更新するための応答。"""
    context = leaderboard_context()
    return jsonify(
        html=render_template('_leaderboard_results.html', **context),
        filters=context['filters'],
    )


@app.route('/models/<int:model_id>')
def model_detail(model_id: int) -> str:
    """モデルの基本情報と全評価結果を表示する。"""
    db = get_db()
    model = db.execute(
        'SELECT m.model_id, m.model_name, o.organization_name, l.license_name '
        'FROM models m '
        'JOIN organizations o ON m.organization_id = o.organization_id '
        'JOIN licenses l ON m.license_id = l.license_id '
        'WHERE m.model_id = ?', (model_id,)
    ).fetchone()
    if model is None:
        abort(404)
    results = db.execute(
        'SELECT a.arena_name, r.category, r.leaderboard_publish_date, r.rank, '
        'r.rating, r.rating_lower, r.rating_upper, r.vote_count '
        'FROM leaderboard_results r JOIN arenas a ON r.arena_id = a.arena_id '
        'WHERE r.model_id = ? ORDER BY r.leaderboard_publish_date DESC, r.rank',
        (model_id,)
    ).fetchall()
    return render_template('model_detail.html', model=model, results=results)


@app.route('/organizations')
def organization_leaderboard() -> str:
    """開発組織ごとの評価結果を集計したランキングを表示する。"""
    ranking_metrics = {
        'model_count': ('掲載モデル数', 'model_count DESC, avg_rating DESC, max_rating DESC'),
        'avg_rating': ('平均レート', 'avg_rating DESC, max_rating DESC, model_count DESC'),
        'max_rating': ('最高レート', 'max_rating DESC, avg_rating DESC, model_count DESC'),
    }
    metric = request.args.get('metric', default='avg_rating', type=str)
    direction = request.args.get('direction', default='desc', type=str)
    if metric not in ranking_metrics:
        metric = 'avg_rating'
    if direction not in {'asc', 'desc'}:
        direction = 'desc'
    filters = {
        'arena': request.args.get('arena', type=int),
        'category': request.args.get('category', default='', type=str).strip(),
        'date': request.args.get('date', default='', type=str).strip(),
        'metric': metric,
        'direction': direction,
    }
    apply_default_leaderboard_filters(filters)
    clauses: list[str] = []
    params: list[object] = []
    column_map = {
        'arena': 'a.arena_id',
        'category': 'v.category',
        'date': 'v.leaderboard_publish_date',
    }
    for key, column in column_map.items():
        value = filters[key]
        if value:
            clauses.append(f'{column} = ?')
            params.append(value)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    db = get_db()
    total_records = db.execute(
        'SELECT COUNT(*) FROM ('
        'SELECT v.organization_name '
        'FROM leaderboard_result_view v '
        'JOIN arenas a ON a.arena_name = v.arena_name '
        f'{where} GROUP BY v.organization_name'
        ')',
        params,
    ).fetchone()[0]
    total_pages = max(1, (total_records + PAGE_SIZE - 1) // PAGE_SIZE)
    current_page = max(1, request.args.get('page', default=1, type=int) or 1)
    current_page = min(current_page, total_pages)
    offset = (current_page - 1) * PAGE_SIZE
    organizations = db.execute(
        'SELECT o.organization_id, v.organization_name, '
        'COUNT(DISTINCT v.model_name) AS model_count, '
        'ROUND(AVG(v.rating), 2) AS avg_rating, '
        'ROUND(MAX(v.rating), 2) AS max_rating '
        'FROM leaderboard_result_view v '
        'JOIN organizations o ON o.organization_name = v.organization_name '
        'JOIN arenas a ON a.arena_name = v.arena_name '
        f'{where} '
        'GROUP BY o.organization_id, v.organization_name '
        f'ORDER BY {metric} {direction.upper()}, v.organization_name '
        'LIMIT ? OFFSET ?',
        [*params, PAGE_SIZE, offset],
    ).fetchall()
    models_by_organization: dict[int, list[sqlite3.Row]] = {}
    organization_ids = [row['organization_id'] for row in organizations]
    if organization_ids:
        placeholders = ', '.join('?' for _ in organization_ids)
        model_clauses = [f'm.organization_id IN ({placeholders})']
        model_params: list[object] = [*organization_ids]
        model_column_map = {
            'arena': 'a.arena_id',
            'category': 'r.category',
            'date': 'r.leaderboard_publish_date',
        }
        for key, column in model_column_map.items():
            value = filters[key]
            if value:
                model_clauses.append(f'{column} = ?')
                model_params.append(value)
        model_rows = db.execute(
            'SELECT m.organization_id, m.model_id, m.model_name, '
            'l.license_name, ROUND(MAX(r.rating), 2) AS max_rating '
            'FROM models m '
            'JOIN licenses l ON l.license_id = m.license_id '
            'JOIN leaderboard_results r ON r.model_id = m.model_id '
            'JOIN arenas a ON a.arena_id = r.arena_id '
            f"WHERE {' AND '.join(model_clauses)} "
            'GROUP BY m.organization_id, m.model_id, m.model_name, l.license_name '
            'ORDER BY m.organization_id, max_rating DESC, m.model_name',
            model_params,
        ).fetchall()
        for row in model_rows:
            models_by_organization.setdefault(row['organization_id'], []).append(row)
    active_filters = {key: value for key, value in filters.items() if value}
    sort_filters = {
        key: value for key, value in active_filters.items()
        if key not in {'metric', 'direction'}
    }
    sort_directions = {
        column: (
            'asc' if metric != column
            else ('asc' if direction == 'desc' else 'desc')
        )
        for column in ranking_metrics
    }
    return render_template(
        'organization_leaderboard.html', organizations=organizations,
        models_by_organization=models_by_organization,
        filters=filters,
        filter_options=fetch_filter_options(filters['arena'], filters['category']),
        total_records=total_records, current_page=current_page,
        total_pages=total_pages,
        page_links=pagination_links(current_page, total_pages),
        active_filters=active_filters,
        ranking_metrics=ranking_metrics,
        sort_filters=sort_filters, sort_directions=sort_directions,
    )


@app.route('/organizations/<int:organization_id>')
def organization_detail(organization_id: int) -> str:
    """組織ごとの集計とモデルの評価結果を表示する。"""
    db = get_db()
    organization = db.execute(
        'SELECT * FROM organizations WHERE organization_id = ?', (organization_id,)
    ).fetchone()
    if organization is None:
        abort(404)
    summary = db.execute(
        'SELECT COUNT(DISTINCT m.model_id) AS model_count, '
        'ROUND(AVG(r.rating), 2) AS avg_rating, ROUND(MAX(r.rating), 2) AS max_rating '
        'FROM models m JOIN leaderboard_results r ON m.model_id = r.model_id '
        'WHERE m.organization_id = ?', (organization_id,)
    ).fetchone()
    results = db.execute(
        'SELECT m.model_id, m.model_name, a.arena_name, r.category, '
        'r.leaderboard_publish_date, r.rank, r.rating, r.vote_count '
        'FROM leaderboard_results r '
        'JOIN models m ON r.model_id = m.model_id '
        'JOIN arenas a ON r.arena_id = a.arena_id '
        'WHERE m.organization_id = ? '
        'ORDER BY r.rating DESC, r.rank ASC', (organization_id,)
    ).fetchall()
    return render_template(
        'organization_detail.html', organization=organization, summary=summary,
        results=results
    )


@app.route('/licenses')
def license_leaderboard() -> str:
    """ライセンスごとの評価結果を集計したランキングを表示する。"""
    ranking_metrics = {
        'model_count': ('掲載モデル数', 'model_count DESC, avg_rating DESC, max_rating DESC'),
        'avg_rating': ('平均レート', 'avg_rating DESC, max_rating DESC, model_count DESC'),
        'max_rating': ('最高レート', 'max_rating DESC, avg_rating DESC, model_count DESC'),
    }
    metric = request.args.get('metric', default='avg_rating', type=str)
    direction = request.args.get('direction', default='desc', type=str)
    if metric not in ranking_metrics:
        metric = 'avg_rating'
    if direction not in {'asc', 'desc'}:
        direction = 'desc'
    filters = {
        'arena': request.args.get('arena', type=int),
        'category': request.args.get('category', default='', type=str).strip(),
        'date': request.args.get('date', default='', type=str).strip(),
        'metric': metric,
        'direction': direction,
    }
    apply_default_leaderboard_filters(filters)
    clauses: list[str] = []
    params: list[object] = []
    column_map = {
        'arena': 'a.arena_id',
        'category': 'v.category',
        'date': 'v.leaderboard_publish_date',
    }
    for key, column in column_map.items():
        value = filters[key]
        if value:
            clauses.append(f'{column} = ?')
            params.append(value)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ''
    db = get_db()
    total_records = db.execute(
        'SELECT COUNT(*) FROM ('
        'SELECT v.license_name '
        'FROM leaderboard_result_view v '
        'JOIN arenas a ON a.arena_name = v.arena_name '
        f'{where} GROUP BY v.license_name'
        ')',
        params,
    ).fetchone()[0]
    total_pages = max(1, (total_records + PAGE_SIZE - 1) // PAGE_SIZE)
    current_page = max(1, request.args.get('page', default=1, type=int) or 1)
    current_page = min(current_page, total_pages)
    offset = (current_page - 1) * PAGE_SIZE
    licenses = db.execute(
        'SELECT l.license_id, v.license_name, '
        'COUNT(DISTINCT v.model_name) AS model_count, '
        'ROUND(AVG(v.rating), 2) AS avg_rating, '
        'ROUND(MAX(v.rating), 2) AS max_rating '
        'FROM leaderboard_result_view v '
        'JOIN licenses l ON l.license_name = v.license_name '
        'JOIN arenas a ON a.arena_name = v.arena_name '
        f'{where} '
        'GROUP BY l.license_id, v.license_name '
        f'ORDER BY {metric} {direction.upper()}, v.license_name '
        'LIMIT ? OFFSET ?',
        [*params, PAGE_SIZE, offset],
    ).fetchall()
    models_by_license: dict[int, list[sqlite3.Row]] = {}
    license_ids = [row['license_id'] for row in licenses]
    if license_ids:
        placeholders = ', '.join('?' for _ in license_ids)
        model_clauses = [f'm.license_id IN ({placeholders})']
        model_params: list[object] = [*license_ids]
        model_column_map = {
            'arena': 'a.arena_id',
            'category': 'r.category',
            'date': 'r.leaderboard_publish_date',
        }
        for key, column in model_column_map.items():
            value = filters[key]
            if value:
                model_clauses.append(f'{column} = ?')
                model_params.append(value)
        model_rows = db.execute(
            'SELECT m.license_id, m.model_id, m.model_name, '
            'o.organization_name, COUNT(r.result_id) AS result_count, '
            'ROUND(MAX(r.rating), 2) AS max_rating '
            'FROM models m '
            'JOIN organizations o ON o.organization_id = m.organization_id '
            'JOIN leaderboard_results r ON r.model_id = m.model_id '
            'JOIN arenas a ON a.arena_id = r.arena_id '
            f"WHERE {' AND '.join(model_clauses)} "
            'GROUP BY m.license_id, m.model_id, m.model_name, o.organization_name '
            'ORDER BY m.license_id, max_rating DESC, m.model_name',
            model_params,
        ).fetchall()
        for row in model_rows:
            models_by_license.setdefault(row['license_id'], []).append(row)
    active_filters = {key: value for key, value in filters.items() if value}
    sort_filters = {
        key: value for key, value in active_filters.items()
        if key not in {'metric', 'direction'}
    }
    sort_directions = {
        column: (
            'asc' if metric != column
            else ('asc' if direction == 'desc' else 'desc')
        )
        for column in ranking_metrics
    }
    return render_template(
        'license_leaderboard.html', licenses=licenses, filters=filters,
        models_by_license=models_by_license,
        filter_options=fetch_filter_options(filters['arena'], filters['category']),
        total_records=total_records, current_page=current_page,
        total_pages=total_pages,
        page_links=pagination_links(current_page, total_pages),
        active_filters=active_filters, ranking_metrics=ranking_metrics,
        sort_filters=sort_filters, sort_directions=sort_directions,
    )


@app.route('/licenses/<int:license_id>')
def license_models(license_id: int) -> str:
    """ライセンスに対応するモデルの一覧を表示する。"""
    db = get_db()
    license_row = db.execute(
        'SELECT * FROM licenses WHERE license_id = ?', (license_id,)
    ).fetchone()
    if license_row is None:
        abort(404)
    models = db.execute(
        'SELECT m.model_id, m.model_name, o.organization_id, o.organization_name, '
        'COUNT(r.result_id) AS result_count, ROUND(MAX(r.rating), 2) AS max_rating '
        'FROM models m '
        'JOIN organizations o ON m.organization_id = o.organization_id '
        'LEFT JOIN leaderboard_results r ON m.model_id = r.model_id '
        'WHERE m.license_id = ? '
        'GROUP BY m.model_id, m.model_name, o.organization_id, o.organization_name '
        'ORDER BY m.model_name', (license_id,)
    ).fetchall()
    return render_template('license_models.html', license=license_row, models=models)


@app.errorhandler(404)
def not_found(error: object) -> tuple[str, int]:
    """存在しないリソースへのアクセスを案内する。"""
    return render_template('not_found.html'), 404
