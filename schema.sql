CREATE TABLE file_tag (f TEXT NOT NULL, t TEXT NOT NULL);
CREATE TABLE impl (t1 TEXT NOT NULL, t2 TEXT NOT NULL);
CREATE VIEW file_tag_w_impl AS
WITH RECURSIVE x(f, t) AS (
    SELECT f, t FROM file_tag
    UNION
    SELECT f, t2 FROM x JOIN impl ON t1 = t
)
SELECT f, t FROM x;
