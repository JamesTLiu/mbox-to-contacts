# mbox_to_sender_emails_with_names
A script to parse a `.mbox` file into a `.json` file showing unique sender (`From` field) email addresses and their sender names across all messages. Emails in the `.mbox` file are sorted by reverse domain components and then by full email.

## Required python package installs
```bash
pip3 install bs4 lxml
```

## Example 1
Use a `.mbox` file.
```python
sender_emails_with_aliases = mbox_to_sender_emails_with_aliases(
    "All mail Including Spam and Trash.mbox",
    "sender_emails_with_aliases.json",
    True,
)
```
A sender fields `.json` file named after the `.mbox` file (`All mail Including Spam and Trash - sender fields.json` in this example) will be created if the last parameter to `mbox_to_sender_emails_with_aliases()` is True. It can be used with `json_mbox_senders_to_sender_emails_with_aliases()` to avoid reparsing the `.mbox` file for efficiency (see Example 2).

## Example 2
Use a previously created sender fields `.json` file instead of reparsing the `.mbox` file for efficiency (most of the processing time in spent on parsing the `.mbox` file).
```python
sender_emails_with_aliases = json_mbox_senders_to_sender_emails_with_aliases(
    "All mail Including Spam and Trash - sender fields.json",
    "sender_emails_with_aliases.json",
)
```

## Credits
Python script to parse mbox files: https://gist.github.com/benwattsjones/060ad83efd2b3afc8b229d41f9b246c4
