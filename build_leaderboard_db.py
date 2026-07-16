"""ローカルの各 arena の full split から leaderboard.db を作成する。"""

import math
import sqlite3
from pathlib import Path

import pandas as pd


DB_PATH = Path(__file__).with_name('leaderboard.db')
BUILD_DB_PATH = Path(__file__).with_name('.leaderboard.building.db')
DATASET_DIR = Path(__file__).with_name('dataset')


def is_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value)


def text(value: object) -> str:
    if is_missing(value) or not str(value).strip():
        return 'Unknown'
    return str(value)


def number(value: object, converter: type[float] | type[int]) -> float | int | None:
    if is_missing(value):
        return None
    if isinstance(value, str):
        value = value.replace(',', '')
    return converter(float(value))


def create_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    PRAGMA foreign_keys = ON;
    DROP VIEW IF EXISTS leaderboard_result_view;
    DROP TABLE IF EXISTS leaderboard_results;
    DROP TABLE IF EXISTS models;
    DROP TABLE IF EXISTS arenas;
    DROP TABLE IF EXISTS organizations;
    DROP TABLE IF EXISTS licenses;

    CREATE TABLE organizations (
      organization_id INTEGER PRIMARY KEY,
      organization_name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE licenses (
      license_id INTEGER PRIMARY KEY,
      license_name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE models (
      model_id INTEGER PRIMARY KEY,
      model_name TEXT NOT NULL UNIQUE,
      organization_id INTEGER NOT NULL REFERENCES organizations(organization_id),
      license_id INTEGER NOT NULL REFERENCES licenses(license_id)
    );
    CREATE TABLE arenas (
      arena_id INTEGER PRIMARY KEY,
      arena_name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE leaderboard_results (
      result_id INTEGER PRIMARY KEY,
      model_id INTEGER NOT NULL REFERENCES models(model_id),
      arena_id INTEGER NOT NULL REFERENCES arenas(arena_id),
      category TEXT NOT NULL,
      leaderboard_publish_date TEXT NOT NULL,
      rank INTEGER NOT NULL,
      rating REAL NOT NULL,
      rating_lower REAL,
      rating_upper REAL,
      variance REAL,
      vote_count INTEGER,
      UNIQUE (model_id, arena_id, category, leaderboard_publish_date)
    );
    CREATE INDEX idx_results_rank_rating ON leaderboard_results(rank, rating DESC);
    CREATE INDEX idx_results_variance ON leaderboard_results(variance DESC);
    CREATE INDEX idx_results_filter ON leaderboard_results(
      arena_id, category, leaderboard_publish_date
    );
    CREATE INDEX idx_models_organization ON models(organization_id);
    CREATE INDEX idx_models_license ON models(license_id);
    CREATE VIEW leaderboard_result_view AS
    SELECT r.result_id, m.model_name, o.organization_name, l.license_name,
           a.arena_name, r.category, r.leaderboard_publish_date, r.rank,
           r.rating, r.rating_lower, r.rating_upper, r.variance, r.vote_count
    FROM leaderboard_results r
    JOIN models m ON r.model_id = m.model_id
    JOIN organizations o ON m.organization_id = o.organization_id
    JOIN licenses l ON m.license_id = l.license_id
    JOIN arenas a ON r.arena_id = a.arena_id;
    """)


def get_id(connection: sqlite3.Connection, table: str, id_column: str,
           name_column: str, value: object) -> int:
    value = text(value)
    connection.execute(
        f'INSERT OR IGNORE INTO {table} ({name_column}) VALUES (?)', (value,)
    )
    return connection.execute(
        f'SELECT {id_column} FROM {table} WHERE {name_column} = ?', (value,)
    ).fetchone()[0]


def insert_records(connection: sqlite3.Connection, records: pd.DataFrame) -> None:
    for row in records.to_dict(orient='records'):
        rank = number(row.get('rank'), int)
        rating = number(row.get('rating'), float)
        if rank is None or rating is None:
            continue
        organization_id = get_id(connection, 'organizations', 'organization_id', 'organization_name', row.get('organization'))
        license_id = get_id(connection, 'licenses', 'license_id', 'license_name', row.get('license'))
        arena_id = get_id(connection, 'arenas', 'arena_id', 'arena_name', row.get('arena_name'))
        model_name = text(row.get('model_name'))
        connection.execute(
            'INSERT OR IGNORE INTO models (model_name, organization_id, license_id) VALUES (?, ?, ?)',
            (model_name, organization_id, license_id),
        )
        model_id = connection.execute(
            'SELECT model_id FROM models WHERE model_name = ?', (model_name,)
        ).fetchone()[0]
        connection.execute(
            'INSERT OR IGNORE INTO leaderboard_results '
            '(model_id, arena_id, category, leaderboard_publish_date, rank, rating, '
            'rating_lower, rating_upper, variance, vote_count) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (model_id, arena_id, text(row.get('category')),
             text(row.get('leaderboard_publish_date')), rank, rating,
             number(row.get('rating_lower'), float), number(row.get('rating_upper'), float),
             number(row.get('variance'), float), number(row.get('vote_count'), int)),
        )


def load_local_full_splits() -> list[pd.DataFrame]:
    """dataset/<arena名>/full-*.parquet を arena ごとに読み込む。"""
    if not DATASET_DIR.is_dir():
        raise FileNotFoundError(f'dataset directory not found: {DATASET_DIR}')

    frames: list[pd.DataFrame] = []
    arena_directories = sorted(path for path in DATASET_DIR.iterdir() if path.is_dir())
    print(f'found {len(arena_directories)} arenas')
    for arena_directory in arena_directories:
        parquet_paths = sorted(arena_directory.glob('full-*.parquet'))
        if not parquet_paths:
            print(f'skipped {arena_directory.name}: full parquet not found')
            continue
        frame = pd.concat(
            (pd.read_parquet(parquet_path) for parquet_path in parquet_paths),
            ignore_index=True,
        )
        frame['arena_name'] = arena_directory.name
        frames.append(frame)
        print(f'loaded {arena_directory.name}: {len(frame):,} rows')

    if not frames:
        raise FileNotFoundError(f'no full parquet files found in: {DATASET_DIR}')
    return frames


def main() -> None:
    records = pd.concat(load_local_full_splits(), ignore_index=True)
    print(f'total source rows: {len(records):,}')
    if BUILD_DB_PATH.exists():
        BUILD_DB_PATH.unlink()

    try:
        with sqlite3.connect(BUILD_DB_PATH) as connection:
            create_tables(connection)
            insert_records(connection, records)
            arena_count = connection.execute('SELECT COUNT(*) FROM arenas').fetchone()[0]
            result_count = connection.execute(
                'SELECT COUNT(*) FROM leaderboard_results'
            ).fetchone()[0]
            july_8_count = connection.execute(
                "SELECT COUNT(*) FROM leaderboard_results "
                "WHERE leaderboard_publish_date = '2026-07-08'"
            ).fetchone()[0]
        BUILD_DB_PATH.replace(DB_PATH)
    except Exception:
        BUILD_DB_PATH.unlink(missing_ok=True)
        raise

    print(
        f'created {DB_PATH} '
        f'(arenas={arena_count}, results={result_count:,}, july_8={july_8_count})'
    )


if __name__ == '__main__':
    main()
