from __future__ import annotations

import json
import mailbox
import re
from pathlib import Path
from collections import defaultdict
from typing import Any, Iterable, Generator
import sys
import logging
from contextlib import contextmanager
import loguru
from loguru import logger
from gmail_mbox_parser import GmailMboxMessage
import vobject
from vobject import vcard


logger.disable("mylib")
log_path = "log.txt"
num_filtered_records = 0
DEFAULT_OUT_PATH = "contacts.json"


@logger.catch(reraise=True)
def main():
    # usage examples below

    def mbox_from_to_fields_example():
        # Get "From" and "To" contacts from a .mbox file.
        return get_contact_emails_with_names_from_mbox(
            "All mail Including Spam and Trash.mbox",
        )

    def mbox_from_to_fields_and_dump_fields_to_json_example():
        # Get "From" and "To" contacts from a .mbox file and dump "From"
        # and "To" fields to a .json file.
        return get_contact_emails_with_names_from_mbox(
            "All mail Including Spam and Trash.mbox",
            dump_fields_to_json=True,
        )

    def mbox_from_field_example():
        # Get only "From" contacts from a .mbox file and dump "From"
        # fields to a .json file.
        return get_contact_emails_with_names_from_mbox(
            "All mail Including Spam and Trash.mbox",
            omit_to_fields=True,
        )

    def mbox_to_field_example():
        # Get only "To" contacts from a .mbox file and dump "To" fields
        # to a .json file.
        return get_contact_emails_with_names_from_mbox(
            "All mail Including Spam and Trash.mbox",
            omit_from_fields=True,
        )

    def json_example():
        # Use a previously created fields .json file (in this case with
        # "From" and "To" fields) instead of reparsing the .mbox file
        # for efficiency.
        return get_contact_emails_with_names_from_json_with_mbox_fields(
            "All mail Including Spam and Trash - From To fields.json",
        )

    mbox_from_to_fields_example()


def track_num_filtered(fn: loguru.FilterFunction):
    def inner(*args, **kwargs):
        passes_filter = fn(*args, **kwargs)

        if not passes_filter:
            global num_filtered_records
            num_filtered_records += 1

        return passes_filter

    return inner


def level_filter(*levels: str) -> loguru.FilterFunction:
    """Return a filter function for logging handlers that only allows
    records with the specified log levels"""

    @track_num_filtered
    def is_level(record: loguru.Record) -> bool:
        return record["level"].name in levels

    return is_level


@contextmanager
def print_warnings_summary():
    try:
        yield
    finally:
        if num_filtered_records:
            logger.info(
                f"{num_filtered_records} warnings found! Please check the log"
                " file to avoid missing potential contacts:"
                f" {Path(log_path).resolve()}."
            )


def _load_json(json_file_path: str) -> Any:
    """Deserialize data in a json file to a Python object.

    Args:
        json_file_path (str): File path of the json file.

    Returns:
        Any: A Python object with the deserialize data.
    """
    with open(json_file_path, "r") as file:
        return json.load(file)


def _dump_to_json_file(data: Any, file_path: str | Path) -> None:
    """Output data to the json file. Overwrites if the file already
    exists.

    Args:
        data (Any): Any serializable data.
        file_path (str | Path): Path for the output json file.
    """
    with open(Path(file_path), "w") as file:
        json.dump(data, file)


def _dump_to_vcf_file(
    emails_with_names: list[tuple[str, tuple[str, ...]]], file_path: str | Path
) -> None:
    """Output emails with names to a vCard (.vcf) file. Overwrites if
    the file already exists.

    Args:
        emails_with_names (list[tuple[str, tuple[str, ...]]]): tuple as
                (email, names).
        file_path (str | Path): Path for the output vcf file.
    """
    with open(Path(file_path), "w", newline="") as file:
        for email, names in emails_with_names:
            # all_valid_chars = re.compile(r"(?i)^[-a-z0-9]+$")
            invalid_chars = re.compile(r"[.;:\n\r]")
            valid_names = [
                name.strip("'\"") for name in names if not invalid_chars.search(name)
            ]
            j = vobject.vCard()
            name = (
                valid_names[0] if valid_names and valid_names[0] else "No name"
            )
            j.add("n")
            j.n.value = vcard.Name(name)
            j.add("fn")
            j.fn.value = name
            j.add("email")
            j.email.value = email.strip("'\"")
            # j.email.type_param = "INTERNET"
            note_value = r"\, ".join(valid_names)

            if note_value:
                j.add("note")
                j.note.value = note_value

            vcard_serialized = j.serialize()
            file.write(vcard_serialized)


def _ensure_is_file(path: Path | str, must_exist=False) -> None:
    """Ensure that the path is to an existing file if must_exist is
    True. Ensure that the path is to an existing file or doesn't exist
    if must_exist is False.

    Args:
        path (Path | str): A file path.
        must_exist (bool, optional): If True, require that the path must
            exist. Defaults to False.

    Raises:
        ValueError: Path does not exist but must exist. (Only possible
            when must_exist=True)
        ValueError: Path exists but is to a non-file.
    """
    path = Path(path)
    is_existing_file = path.is_file()
    is_existing_path = path.exists()
    abs_path = path.resolve()

    if must_exist and not is_existing_path:
        raise ValueError(f"Path does not exist but must exist: {abs_path}")
    elif is_existing_path and not is_existing_file:
        raise ValueError(f"Path exists but is to a non-file: {abs_path}")


def _ensure_existing_file(path: str | Path, suffix: str = "") -> None:
    """Ensure an existing file is at the path. Optionally, ensure that
    the file has a specific suffix.

    Args:
        path (str | Path): A file path.
        suffix (str, optional): If a non-empty string, ensures that the
            file has the same suffix. Defaults to "".

    Raises:
        ValueError: Path to file exists but has an incorrect suffix.
    """
    path = Path(path)
    _ensure_is_file(path, must_exist=True)

    if suffix and path.suffix != suffix:
        raise ValueError(
            f"Path to file exists but is not to a {suffix} file:"
            f" {path.resolve()}"
        )


def _ensure_existing_mbox_file(path: Path | str) -> None:
    """Ensure an existing .mbox file is at the path.

    Args:
        path (Path | str): A file path.
    """
    _ensure_existing_file(path, suffix=".mbox")


def _ensure_existing_json_file(path: Path | str) -> None:
    """Ensure an existing .json file is at the path

    Args:
        path (Path | str): A file path.
    """
    _ensure_existing_file(path, suffix=".json")


def _mbox_fields_to_email_and_names_dict(
    mbox_fields: Iterable[str],
) -> defaultdict[str, set]:
    """Convert mbox messages to a dict mapping emails to their
    associated names.

    Args:
        mbox_fields (Iterable[str]): The fields of a .mbox file.

    Returns:
        defaultdict[str, set]: A dict mapping emails to their associated
            names.
    """
    email_to_names = defaultdict(set)

    name_regex = r"(?P<name>[^<>,]*?)[<]?"
    # https://stackabuse.com/python-validate-email-address-with-regular-expressions-regex/
    email_regex = r"(?P<email>([-!#-'*+/-9=?A-Z^-~]+(\.[-!#-'*+/-9=?A-Z^-~]+)*|\"([]!#-[^-~ \t]|(\\[\t -~]))+\")@([-!#-'*+/-9=?A-Z^-~]+(\.[-!#-'*+/-9=?A-Z^-~]+)*|\[[\t -Z^-~]*]))"  # noqa: E501
    name_email_regex = name_regex + email_regex

    for field in mbox_fields:
        matches = re.finditer(name_email_regex, field)

        exists_match = False

        for match in matches:
            email = match.group("email").strip()
            name = match.group("name").strip()

            if name:
                email_to_names[email].add(name)
            else:
                email_to_names[email]

            exists_match = True

        if not exists_match:
            logger.warning(f"Skipping - No email(s) found in field: {field}")
            continue

    return email_to_names


def _dict_with_set_to_hashable(
    email_to_name: dict[str, set[str]]
) -> Generator[tuple[str, tuple[str, ...]], None, None]:
    """Return a hashable version of a dict mapping emails to their
    associated names.

    Args:
        email_to_name (dict[str, set]): A dict mapping emails to
            their associated names.

    Yields:
        Generator[tuple[str, tuple], None, None]: _description_
    """
    return ((email, tuple(names)) for email, names in email_to_name.items())


def _parse_mbox_file_to_contacts_fields_list(
    mbox_file_path: str, omit_from_fields=False, omit_to_fields=False
) -> list[str]:
    """Return a list with the "From" and "To" fields in the mbox file.

    Args:
        mbox_file_path (str): The path to the mbox file.
        omit_from_fields (bool, optional): If True, "From" fields will
            be ignored. Defaults to False.
        omit_to_fields (bool, optional): If True, "To" fields will
            be ignored. Defaults to False.
    Returns:
        list[str]: A list with the fields in the mbox file.
    """
    mb = mailbox.mbox(mbox_file_path)
    num_entries = len(mb)
    contacts_list = []

    if omit_from_fields and omit_to_fields:
        return contacts_list

    for email_obj in mb:
        email_data = GmailMboxMessage(email_obj)
        email_data.parse_email()

        if not omit_from_fields:
            if email_data.email_from:
                contacts_list.append(email_data.email_from)
            else:
                logger.warning(
                    f"skipping mbox message - empty 'From:': {email_data}"
                )

        if not omit_to_fields:
            if email_data.email_to:
                contacts_list.append(email_data.email_to)
            else:
                logger.warning(
                    f"skipping mbox message - empty 'To:': {email_data}"
                )

    logger.info(f"entries in '{mbox_file_path}': {num_entries}")
    return contacts_list


def _mbox_fields_to_emails_with_names(
    mbox_fields: Iterable[str], out_file_path: str | Path | None = None
) -> list[tuple[str, tuple]]:
    """Convert mbox fields to a list of (email, names) tuples.
    List is sorted by the domain components in reverse and then by the
    full email address. Writes the results to files based on the
    specified path or based on the default path if no path is given.

    Result files: a json file with contact email addresses and their
    associated names, a json file with only contact email addresses, and
    a vCard (vcf) file with contact email addresses and their
    associated names (all associated names will be in the Notes property
    while only the first name will be used for the Full Name (FN)
    property).

    Args:
        mbox_fields (Iterable[str]): The fields from mbox messages.
        out_file_path (str, Path, optional): The path to the file to
            write the result to in json. If no path is given,
            a default path will be used. Defaults to None.

    Raises:
        ValueError: @ not found in an email.

    Returns:
        list[tuple[str, tuple]]: A list of (email, names) tuples.
            names is a tuple with all names for the email.
    """
    email_to_names = _mbox_fields_to_email_and_names_dict(mbox_fields)
    hashable_email_to_names = _dict_with_set_to_hashable(email_to_names)

    def to_domain_components_and_email(
        email_with_names: tuple[str, tuple[str, ...]]
    ) -> tuple[str, ...]:
        """Return  the domain components in reverse followed by the
        email given the email and its associated names).

        Args:
            email_with_names (tuple[str, tuple[str, ...]]): tuple as
                (email, names).

        Raises:
            ValueError: Invalid email: no @ in the email.
            ValueError: Invalid email: more than 1 @ in email.
            ValueError: Invalid email: no domain found (nothing after
                @).

        Returns:
            tuple[str, ...]: A tuple with the domain components in
                reverse followed by the email.
        """
        email, _ = email_with_names
        email = email.strip().lower()
        num_ats = email.count("@")

        if num_ats < 1:
            raise ValueError(f"Invalid email: no @ in the email: '{email}'")
        elif num_ats > 1:
            raise ValueError("Invalid email: more than 1 @ in the email!")

        domain = email.split("@")[1]

        if not domain:
            raise ValueError(
                f"Invalid email: no domain found (nothing after @): '{email}'"
            )

        domain_parts = re.split(r"\W", domain)
        domain_parts.reverse()

        return (*domain_parts, email)

    emails_with_names = sorted(
        hashable_email_to_names, key=to_domain_components_and_email
    )

    if not out_file_path:
        out_file_path = DEFAULT_OUT_PATH

    out_file_path = Path(out_file_path)

    _dump_to_json_file(emails_with_names, out_file_path)
    logger.info(
        "contact email addresses with their names written to"
        f" '{out_file_path.resolve()}"
    )

    emails_only_out_file_path = out_file_path.with_stem(
        "emails only - " + out_file_path.stem
    )

    emails_only = tuple(email for email, _ in emails_with_names)

    _dump_to_json_file(emails_only, emails_only_out_file_path)
    logger.info(
        "contact email addresses written to"
        f" '{emails_only_out_file_path.resolve()}"
    )

    vcf_out_file_path = out_file_path.with_name("contacts.vcf")

    _dump_to_vcf_file(emails_with_names, vcf_out_file_path)
    logger.info(f"contact vCards written to '{vcf_out_file_path.resolve()}")

    return emails_with_names


@print_warnings_summary()
def get_contact_emails_with_names_from_json_with_mbox_fields(
    json_file_path: str, out_file_path: str | Path | None = None
) -> list[tuple[str, tuple[str, ...]]]:
    """Import mbox fields from a json file and convert them into
    a list of (email, names) tuples. List is sorted by the domain
    components in reverse, then by email. Writes the result to the
    specified path or to a default path if no path is given.

    Result files: a json file with contact email addresses and their
    associated names, a json file with only contact email addresses, and
    a vCard (vcf) file with contact email addresses and their
    associated names (all associated names will be in the Notes property
    while only the first name will be used for the Full Name (FN)
    property).

    Args:
        json_file_path (str): File path for the json file with a list of
            fields (str) from mbox messages.
        out_file_path (str, Path, optional): The path to the file to
            write the result to in json. If no path is given, a default
            path will be used. Defaults to None.

    Returns:
        list[tuple[str, tuple[str, ...]]]: A list of (email, names)
            tuples. names is a tuple with all names associated with the
            email.
    """
    if out_file_path:
        _ensure_is_file(out_file_path)

    _ensure_existing_json_file(json_file_path)

    fields = _load_json(json_file_path)

    return _mbox_fields_to_emails_with_names(fields, out_file_path)


@print_warnings_summary()
def get_contact_emails_with_names_from_mbox(
    mbox_file_path: str,
    out_file_path: str | Path | None = None,
    dump_fields_to_json=False,
    omit_from_fields: bool = False,
    omit_to_fields: bool = False,
) -> list[tuple[str, tuple[str, ...]]]:
    """Return a list of (email, names) tuples for the messages in
    the mbox file. names is a tuple with all names associated
    with the email.

    Result files: a json file with contact email addresses and their
    associated names, a json file with only contact email addresses, and
    a vCard (vcf) file with contact email addresses and their
    associated names (all associated names will be in the Notes property
    while only the first name will be used for the Full Name (FN)
    property).

    Args:
        mbox_file_path (str): The path to the mbox file.
        out_file_path (str, Path, optional): The path to the file to
            write the result to in json. If no path is given, a default
            path will be used.Defaults to None.
        dump_fields_to_json (bool, optional): If True, the fields from
            the mbox file will be output to a json file. Defaults to
            None.

    Returns:
        list[tuple[str, tuple[str, ...]]]: A list of (email, names)
            tuples. names is a tuple with all names associated with the
            email.
    """
    if out_file_path:
        _ensure_is_file(out_file_path)

    _ensure_existing_mbox_file(mbox_file_path)

    if omit_from_fields and omit_to_fields:
        logger.warning(
            "Warning: 'From' and 'To' fields have both been omitted from the"
            " results."
        )
        return []

    fields = _parse_mbox_file_to_contacts_fields_list(
        mbox_file_path,
        omit_from_fields=omit_from_fields,
        omit_to_fields=omit_to_fields,
    )

    if dump_fields_to_json:
        mbox_path = Path(mbox_file_path)
        field_types = []

        if omit_from_fields and omit_to_fields:
            field_types.append("No")
        else:
            if not omit_from_fields:
                field_types.append("From")

            if not omit_to_fields:
                field_types.append("To")

        field_types_str = " ".join(field_types)

        dump_json_path = mbox_path.parent / (
            mbox_path.stem + " - " + field_types_str + " fields.json"
        )

        _dump_to_json_file(fields, dump_json_path)
        logger.info(f"mbox fields written to '{dump_json_path.resolve()}'")

    return _mbox_fields_to_emails_with_names(fields, out_file_path)


if __name__ == "__main__":
    default_logging_format = (
        "{time:MMMM D, YYYY > HH:mm:ss} | {level} | {message} | {extra}"
    )

    logger.enable("mylib")
    logger.remove()
    logger.add(
        log_path,
        mode="w",
        level=logging.DEBUG,
        enqueue=True,
        backtrace=True,
        diagnose=True,
        format=default_logging_format,
    )

    console_output_format = "{message}"

    logger.add(
        sys.stdout,
        level=logging.DEBUG,
        enqueue=True,
        backtrace=True,
        diagnose=True,
        format=console_output_format,
        filter=level_filter("INFO", "SUCCESS"),
    )

    main()
