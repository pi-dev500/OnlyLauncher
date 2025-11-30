```python
    ## PortableMC auth database
    # This code is used to store authentication data for the PortableMC launcher.
    def load(self):

        self.sessions.clear()

        try:
            with self.file.open("rt") as fp:
                data = json.load(fp)
                self.client_id = data.get("client_id")
                for typ, sess_type in self.types.items():
                    typ_data = data.get(typ)
                    if typ_data is not None:
                        sessions = self.sessions[typ] = {}
                        sessions_data = typ_data["sessions"]
                        for email, sess_data in sessions_data.items():
                            # Use class method fix_data to migrate data from older versions of the auth database.
                            sess_type.fix_data(sess_data)
                            sess = sess_type()
                            for field in sess_type.fields:
                                setattr(sess, field, sess_data.get(field, ""))
                            sessions[email.casefold()] = sess
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            pass

    def save(self) -> None:

        self.file.parent.mkdir(parents=True, exist_ok=True)

        with self.file.open("wt") as fp:
            data = {}
            if self.client_id is not None:
                data["client_id"] = self.client_id
            for typ, sessions in self.sessions.items():
                if typ not in self.types:
                    continue
                sess_type = self.types[typ]
                sessions_data = {}
                data[typ] = {"sessions": sessions_data}
                for email, sess in sessions.items():
                    sess_data = sessions_data[email] = {}
                    for field in sess_type.fields:
                        sess_data[field] = getattr(sess, field)
            json.dump(data, fp, indent=2)
```