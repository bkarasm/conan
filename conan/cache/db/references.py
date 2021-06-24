import time

from conan.cache.conan_reference import ConanReference
from conan.cache.db.table import BaseDbTable
from conans.errors import ConanException


class ReferencesDbTable(BaseDbTable):
    table_name = 'conan_references'
    columns_description = [('reference', str),
                           ('rrev', str),
                           ('pkgid', str, True),
                           ('prev', str, True),
                           ('path', str, False, None, True),
                           ('remote', str, True),
                           ('timestamp', float),
                           ('build_id', str, True)]
    unique_together = ('reference', 'rrev', 'pkgid', 'prev')

    class ReferenceDoesNotExist(ConanException):
        pass

    class ReferenceAlreadyExist(ConanException):
        pass

    @staticmethod
    def _as_dict(row):
        return {
            "reference": row.reference,
            "rrev": row.rrev,
            "pkgid": row.pkgid,
            "build_id": row.build_id,
            "prev": row.prev,
            "path": row.path,
            "timestamp": row.timestamp,
            "remote": row.remote
        }

    def _where_clause(self, ref: ConanReference):
        where_dict = {
            self.columns.reference: ref.reference,
            self.columns.rrev: ref.rrev,
            self.columns.pkgid: ref.pkgid,
            self.columns.prev: ref.prev,
        }
        where_expr = ' AND '.join(
            [f'{k}="{v}" ' if v is not None else f'{k} IS NULL' for k, v in where_dict.items()])
        return where_expr

    def _set_clause(self, ref: ConanReference, path=None, timestamp=None, remote=None,
                    build_id=None):
        set_dict = {
            self.columns.reference: ref.reference,
            self.columns.rrev: ref.rrev,
            self.columns.pkgid: ref.pkgid,
            self.columns.prev: ref.prev,
            self.columns.path: path,
            self.columns.timestamp: timestamp,
            self.columns.remote: remote,
            self.columns.build_id: build_id,
        }
        set_expr = ', '.join([f'{k} = "{v}"' for k, v in set_dict.items() if v is not None])
        return set_expr

    def get(self, conn, ref: ConanReference):
        """ Returns the row matching the reference or fails """
        where_clause = self._where_clause(ref)
        query = f'SELECT * FROM {self.table_name} ' \
                f'WHERE {where_clause};'
        r = conn.execute(query)
        row = r.fetchone()
        if not row:
            raise ReferencesDbTable.ReferenceDoesNotExist(
                f"No entry for reference '{ref.full_reference}'")
        return self._as_dict(self.row_type(*row))

    def get_remote(self, conn, ref: ConanReference):
        """ Returns the row matching the reference or fails """
        where_clause = self._where_clause(ref)
        query = f'SELECT {self.columns.remote} FROM {self.table_name} ' \
                f'WHERE {where_clause};'
        r = conn.execute(query)
        row = r.fetchone()
        if not row:
            raise ReferencesDbTable.ReferenceDoesNotExist(
                f"No entry for reference '{ref.full_reference}'")
        return row[0]

    def get_build_id(self, conn, ref: ConanReference):
        """ Returns the row matching the reference or fails """
        assert ref.rrev, "To get the build_id you must provide a recipe revision."
        assert ref.pkgid, "To get the build_id you must provide a package id."
        assert ref.prev, "To get the build_id you must provide a package revision."
        where_clause = self._where_clause(ref)
        query = f'SELECT {self.columns.build_id} FROM {self.table_name} ' \
                f'WHERE {where_clause};'
        r = conn.execute(query)
        row = r.fetchone()
        if not row:
            raise ReferencesDbTable.ReferenceDoesNotExist(
                f"No entry for reference '{ref.full_reference}'")
        return row[0]

    def get_timestamp(self, conn, ref: ConanReference):
        """ Returns the row matching the reference or fails """
        where_clause = self._where_clause(ref)
        query = f'SELECT {self.columns.timestamp} FROM {self.table_name} ' \
                f'WHERE {where_clause};'
        r = conn.execute(query)
        row = r.fetchone()
        if not row:
            raise ReferencesDbTable.ReferenceDoesNotExist(
                f"No entry for reference '{ref.full_reference}'")
        return row[0]

    def save(self, conn, path, ref: ConanReference, remote=None):
        # we set the timestamp to 0 until they get a complete reference, here they
        # are saved with the temporary uuid one, we don't want to consider these
        # not yet built packages for search and so on
        timestamp = 0
        placeholders = ', '.join(['?' for _ in range(len(self.columns))])
        r = conn.execute(f'INSERT INTO {self.table_name} '
                         f'VALUES ({placeholders})',
                         [ref.reference, ref.rrev, ref.pkgid, ref.prev, path, remote, timestamp,
                          None])
        return r.lastrowid

    def set_remote(self, conn, ref: ConanReference, remote):
        where_clause = self._where_clause(ref)
        mew_remote = f'"{remote}"' if remote else 'NULL'
        query = f"UPDATE {self.table_name} " \
                f"SET {self.columns.remote}={mew_remote} " \
                f"WHERE {where_clause};"
        r = conn.execute(query)
        return r.lastrowid

    def update(self, conn, old_ref: ConanReference, new_ref: ConanReference = None, new_path=None,
               new_remote=None, new_build_id=None):
        if not new_ref:
            new_ref = old_ref
        timestamp = time.time()
        where_clause = self._where_clause(old_ref)
        set_clause = self._set_clause(new_ref, path=new_path, timestamp=timestamp,
                                      remote=new_remote, build_id=new_build_id)
        query = f"UPDATE {self.table_name} " \
                f"SET {set_clause} " \
                f"WHERE {where_clause};"
        r = conn.execute(query)
        return r.lastrowid

    def delete_by_path(self, conn, path):
        query = f"DELETE FROM {self.table_name} " \
                f"WHERE path = ?;"
        r = conn.execute(query, (path,))
        return r.lastrowid

    def remove(self, conn, ref: ConanReference):
        where_clause = self._where_clause(ref)
        query = f"DELETE FROM {self.table_name} " \
                f"WHERE {where_clause};"
        r = conn.execute(query)
        return r.lastrowid

    def all(self, conn, only_latest_rrev=False):
        if only_latest_rrev:
            query = f'SELECT DISTINCT {self.columns.reference}, ' \
                    f'{self.columns.rrev}, ' \
                    f'{self.columns.pkgid}, ' \
                    f'{self.columns.prev}, ' \
                    f'{self.columns.path}, ' \
                    f'{self.columns.remote}, ' \
                    f'MAX({self.columns.timestamp}), ' \
                    f'{self.columns.build_id} ' \
                    f'FROM {self.table_name} ' \
                    f'WHERE {self.columns.prev} IS NULL ' \
                    f'GROUP BY {self.columns.reference} ' \
                    f'ORDER BY MAX({self.columns.timestamp}) ASC'
        else:
            query = f'SELECT * FROM {self.table_name} WHERE {self.columns.prev} IS NULL;'
        r = conn.execute(query)
        for row in r.fetchall():
            yield self._as_dict(self.row_type(*row))

    def get_package_revisions(self, conn, ref: ConanReference, only_latest_prev=False):
        assert ref.rrev, "To search for package revisions you must provide a recipe revision."
        assert ref.pkgid, "To search for package revisions you must provide a package id."
        check_prev = f'AND {self.columns.prev} = "{ref.prev}" ' if ref.prev else ''
        if only_latest_prev:
            query = f'SELECT {self.columns.reference}, ' \
                    f'{self.columns.rrev}, ' \
                    f'{self.columns.pkgid}, ' \
                    f'{self.columns.prev}, ' \
                    f'{self.columns.path}, ' \
                    f'{self.columns.remote}, ' \
                    f'MAX({self.columns.timestamp}), ' \
                    f'{self.columns.build_id} ' \
                    f'FROM {self.table_name} ' \
                    f'WHERE {self.columns.rrev} = "{ref.rrev}" ' \
                    f'AND {self.columns.reference} = "{ref.reference}" ' \
                    f'AND {self.columns.pkgid} = "{ref.pkgid}" ' \
                    f'{check_prev} ' \
                    f'AND {self.columns.prev} IS NOT NULL ' \
                    f'GROUP BY {self.columns.pkgid} '
        else:
            query = f'SELECT * FROM {self.table_name} ' \
                    f'WHERE {self.columns.rrev} = "{ref.rrev}" ' \
                    f'AND {self.columns.reference} = "{ref.reference}" ' \
                    f'AND {self.columns.pkgid} = "{ref.pkgid}" ' \
                    f'{check_prev} ' \
                    f'AND {self.columns.prev} IS NOT NULL '
        r = conn.execute(query)
        for row in r.fetchall():
            yield self._as_dict(self.row_type(*row))

    def get_package_ids(self, conn, ref: ConanReference):
        assert ref.rrev, "To search for package id's you must provide a recipe revision."
        # we select the latest prev for each package_id
        query = f'SELECT {self.columns.reference}, ' \
                f'{self.columns.rrev}, ' \
                f'{self.columns.pkgid}, ' \
                f'{self.columns.prev}, ' \
                f'{self.columns.path}, ' \
                f'{self.columns.remote}, ' \
                f'MAX({self.columns.timestamp}), ' \
                f'{self.columns.build_id} ' \
                f'FROM {self.table_name} ' \
                f'WHERE {self.columns.rrev} = "{ref.rrev}" ' \
                f'AND {self.columns.reference} = "{ref.reference}" ' \
                f'AND {self.columns.pkgid} IS NOT NULL ' \
                f'GROUP BY {self.columns.pkgid} '
        r = conn.execute(query)
        for row in r.fetchall():
            yield self._as_dict(self.row_type(*row))

    def get_recipe_revisions(self, conn, ref: ConanReference, only_latest_rrev=False):
        check_rrev = f'AND {self.columns.rrev} = "{ref.rrev}" ' if ref.rrev else ''
        if only_latest_rrev:
            query = f'SELECT {self.columns.reference}, ' \
                    f'{self.columns.rrev}, ' \
                    f'{self.columns.pkgid}, ' \
                    f'{self.columns.prev}, ' \
                    f'{self.columns.path}, ' \
                    f'{self.columns.remote}, ' \
                    f'MAX({self.columns.timestamp}), ' \
                    f'{self.columns.build_id} ' \
                    f'FROM {self.table_name} ' \
                    f'WHERE {self.columns.reference} = "{ref.reference}" ' \
                    f'AND {self.columns.prev} IS NULL ' \
                    f'AND {self.columns.pkgid} IS NULL ' \
                    f'{check_rrev} ' \
                    f'GROUP BY {self.columns.pkgid} '
        else:
            query = f'SELECT * FROM {self.table_name} ' \
                    f'WHERE {self.columns.reference} = "{ref.reference}" ' \
                    f'AND {self.columns.prev} IS NULL ' \
                    f'{check_rrev} ' \
                    f'AND {self.columns.pkgid} IS NULL '

        r = conn.execute(query)
        for row in r.fetchall():
            yield self._as_dict(self.row_type(*row))