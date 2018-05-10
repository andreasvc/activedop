drop table if exists entries;
create table entries (
  sentno integer not null,
  username text not null,
  tree text not null,
  nbest integer not null,
  constraints integer not null,
  dectree integer not null,
  reattach integer not null,
  relabel integer not null,
  reparse integer not null,
  editdist integer not null,
  time integer not null,
  timestamp text not null,
  primary key (sentno, username)
);

