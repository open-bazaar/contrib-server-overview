# bazaar-contrib-server-overview

The overview of the Bazaar Compute server: the first page in the sidebar, where contribs put what is worth a glance and each account arranges it as it likes.

```toml
[[contribs]]
package = "bazaar-contrib-server-overview~=0.3.0rc1"
[[contribs.enabled]]
entry = "server-overview"
```

A contrib puts its content on the overview by accepting `OVERVIEW`.
