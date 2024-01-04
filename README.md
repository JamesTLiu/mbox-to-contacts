# Extract Contact Emails with Names from an MBOX File
A script to parse contacts from a `.mbox` file generated from an email box. Extracted contacts will be in the form of a `.json` file with contact email addresses and their associated names and a `.json` file with only contact email addresses. Email addresses in the `.json` files are sorted so that email addressses with similar domains are close together.

## Get an MBOX File for a GMAIL account
Use [Google Takeout](https://takeout.google.com/settings/takeout/custom/gmail) to download your Mail data in MBOX format.

* Keep the default setting which is "All Mail data included" (click the setting and select "Include all messages in Mail" if it shows otherwise).
* Use whichever file size is desired, but a largest file size will mean runing this script fewer times.
* It may take a while for Google to have the MBOX file ready (a larger mailbox will take longer).

## Install Required Python Packages
It's recommended to do this step in a virtual environment.
```bash
pip3 install -r requirements.txt
```

## Usage Examples
```python
def mbox_from_to_fields_example():
    # Get "From" and "To" contacts from a .mbox file.
    return get_contact_emails_with_names_from_mbox(
        "All mail Including Spam and Trash.mbox",
    )
```

```python
def mbox_from_to_fields_and_dump_fields_to_json_example():
    # Get "From" and "To" contacts from a .mbox file and dump "From" and "To" fields to a .json file.
    return get_contact_emails_with_names_from_mbox(
        "All mail Including Spam and Trash.mbox",
        dump_fields_to_json=True,
    )
```

A `.json` file with fields from the mbox file can be created and will be named after the `.mbox` file. It can be used to recreate the contacts `.json` file while avoiding reparsing the `.mbox` file for efficiency.

```python
def json_example():
    # Use a previously created fields .json file (in this case with "From" and "To" fields) instead of reparsing the .mbox file for efficiency.
    return get_contact_emails_with_names_from_json_with_mbox_fields(
        "All mail Including Spam and Trash - From To fields.json",
    )
```

```python
def mbox_from_field_example():
    # Get only "From" contacts from a .mbox file and dump "From" fields to a .json file.
    return get_contact_emails_with_names_from_mbox(
        "All mail Including Spam and Trash.mbox",
        omit_to_fields=True,
    )
```

```python
def mbox_to_field_example():
    # Get only "To" contacts from a .mbox file and dump "To" fields to a .json file.
    return get_contact_emails_with_names_from_mbox(
        "All mail Including Spam and Trash.mbox",
        omit_from_fields=True,
    )
```

## Check the Log File to Avoid Missing Potential Contacts!
After the script is run, `log.txt` will contain a copy of the command line output as well as any warning messages which are omitted from the command line.

Remember to check the log file if there were warnings to avoid missing potential contacts due to `MBOX` messages or fields being skipped due to being invalid! Sometimes, the fields in the messages of an exported `.mbox` file are different from the actual email's fields!

## Credits
Python script to parse mbox files: https://gist.github.com/benwattsjones/060ad83efd2b3afc8b229d41f9b246c4
