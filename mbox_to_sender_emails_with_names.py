import json
import mailbox
import re
from pathlib import Path
from collections import defaultdict
from typing import *
import sys
import logging
from loguru import logger
from gmail_mbox_parser import GmailMboxMessage

logger.add(
    "log.txt",
    mode="w",
    level=logging.DEBUG,
    enqueue=True,
    backtrace=True,
    diagnose=True,
)

logger.add(
    sys.stdout,
    level=logging.DEBUG,
    enqueue=True,
    backtrace=True,
    diagnose=True,
)


DEFAULT_OUT_PATH = "contacts.json"


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
        file_path (str | Path): Path for the json file to write to.
    """
    with open(Path(file_path), "w") as file:
        json.dump(data, file)


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
    """Convert mbox sender fields to a dict mapping emails to their set
    of sender names.

    Args:
        mbox_fields (Iterable[str]): The sender fields of an
            mbox file.

    Raises:
        ValueError: No sender name + email found in sender field.

    Returns:
        defaultdict[str, set]: A dict mapping emails to their set of
            sender names.
    """
    email_to_names = defaultdict(set)

    for sender in mbox_fields:
        matches = re.finditer(
            r"(?P<name>[^<>,]*)[<]*(?P<email>[\w.]+@[\w.]+)", sender
        )

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
            logger.warning(
                f"Skipping - No sender name + email found in field: {sender}"
            )
            continue

    return email_to_names


def _dict_with_set_to_hashable(
    email_to_sender_name: dict[str, set]
) -> Generator[tuple[str, tuple], None, None]:
    """Return a hashable version of a dict mapping emails to their
    set of sender names.

    Args:
        email_to_sender_name (dict[str, set]): A dict mapping emails to a
            their set of sender names.

    Yields:
        Generator[tuple[str, tuple], None, None]: _description_
    """
    return (
        (email, tuple(sender_names))
        for email, sender_names in email_to_sender_name.items()
    )


def _parse_mbox_file_to_contacts_fields_list(
    mbox_file_path: str, omit_from_fields=False, omit_to_fields=False
) -> list[str]:
    """Return a list with the 'From' and 'To' fields in the mbox file.

    Args:
        mbox_file_path (str): The path to the mbox file.

    Returns:
        list[str]: A list with the sender fields in the mbox file.
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
                    "skipping mbox message - empty 'From:' field:"
                    f" {email_data}"
                )

        if not omit_to_fields:
            if email_data.email_to:
                contacts_list.append(email_data.email_to)
            else:
                logger.warning(
                    f"skipping mbox message - empty 'To:' field: {email_data}"
                )

    logger.info(f"entries in '{mbox_file_path}': {num_entries}")
    return contacts_list


def _mbox_fields_to_emails_with_names(
    mbox_sender_fields: Iterable[str], out_file_path: str | Path | None = None
) -> list[tuple[str, tuple]]:
    """Convert mbox sender fields to a list of (email, sender_names)
    tuples. List is sorted by the @... portion of the email and then the
    email itself. Optionally, writes the result to a file if given.

    Args:
        mbox_sender_fields (Iterable[str]): The sender fields from mbox
            messages.
        out_file_path (str, Path, optional): The path to the file to
            write the result to in json. If no path is given,
            DEFAULT_OUT_PATH will be used. Defaults to None.

    Raises:
        ValueError: @ not found in an email.

    Returns:
        list[tuple[str, tuple]]: A list of (email, sender_names) tuples.
            sender_names is a tuple with all sender names for the email.
    """
    email_to_sender_names = _mbox_fields_to_email_and_names_dict(
        mbox_sender_fields
    )
    hashable_email_to_sender_names = _dict_with_set_to_hashable(
        email_to_sender_names
    )

    def to_domain_and_email(
        email_with_sender_names: tuple[str, Any]
    ) -> tuple[str, str]:
        """Return a tuple as (domain, email) given a tuple with
        (email, sender_names).

        Args:
            email_with_sender_names (tuple[str, Any]): tuple as
                (email, sender_names).

        Raises:
            ValueError: Invalid email: no @ in the email.
            ValueError: Invalid email: more than 1 @ in email section
                and unable to extract the 1st email.
            ValueError: Invalid email: no domain found (nothing after
                @).

        Returns:
            tuple[str, str]: A tuple as
                (part after the @ in an email, email).
        """
        email, _ = email_with_sender_names
        email = email.strip().lower()
        num_ats = email.count("@")

        if num_ats < 1:
            raise ValueError(f"Invalid email: no @ in the email: '{email}'")
        elif num_ats > 1:
            m = re.search(r"[\w.\-]+@[\w.\-]+", email)

            if m:
                email = m.group()
            else:
                raise ValueError(
                    "more than 1 @ in email section and unable to extract"
                    f" the 1st email: '{email}'"
                )

        domain = email.split("@")[1]

        if not domain:
            raise ValueError(
                f"Invalid email: no domain found (nothing after @): '{email}'"
            )

        domain_parts = re.split(r"\W", domain)
        domain_parts.reverse()

        return (*domain_parts, email)

    sender_emails_with_sender_names = sorted(
        hashable_email_to_sender_names, key=to_domain_and_email
    )

    if not out_file_path:
        out_file_path = DEFAULT_OUT_PATH

    _dump_to_json_file(sender_emails_with_sender_names, out_file_path)
    logger.info(
        "mbox email addresses with their names written to"
        f" '{Path(out_file_path).resolve()}"
    )

    return sender_emails_with_sender_names


def get_contact_emails_with_names_from_json_with_mbox_fields(
    json_file_path: str, out_file_path: str | Path | None = None
) -> list[tuple[str, tuple]]:
    """Import mbox sender fields from a json file and convert them into
    a list of (email, sender_names) tuples. List is sorted by the @...
    portion of the email and then the email itself. Optionally, writes
    the result to a file if given.

    Args:
        json_file_path (str): File path for the json file with a list of
            senders (str) of mbox messages.
        out_file_path (str, Path, optional): The path to the file to
            write the result to in json if given. Defaults to None.

    Returns:
        list[tuple[str, tuple]]: A list of (email, sender_names) tuples.
            sender_names is a tuple with all sender names for the email.
    """
    if out_file_path:
        _ensure_is_file(out_file_path)

    _ensure_existing_json_file(json_file_path)

    fields = _load_json(json_file_path)

    return _mbox_fields_to_emails_with_names(fields, out_file_path)


def get_contact_emails_with_names_from_mbox(
    mbox_file_path: str,
    out_file_path: str | Path | None = None,
    dump_fields_to_json=False,
    omit_from_fields: bool = False,
    omit_to_fields: bool = False,
) -> list[tuple[str, tuple]]:
    """Return a list of (email, sender_names) tuples for the messages in
    the mbox file. sender_names is a tuple with all sender names for the
    email.

    Args:
        mbox_file_path (str): The path to the mbox file.
        out_file_path (str, Path, optional): The path to the file to
            write the result to in json if given. Defaults to
            "contacts.json".
        dump_fields_to_json (bool, optional): If True, the fields from
            the mbox file will be output to a json file. Defaults to
            None.

    Returns:
        list[tuple[str, tuple]]: A list of (email, sender_names) tuples.
            sender_names is a tuple with all sender names for the email.
    """
    if out_file_path:
        _ensure_is_file(out_file_path)

    _ensure_existing_mbox_file(mbox_file_path)

    if omit_from_fields and omit_to_fields:
        logger.warning(f"Warning: From and To fields have both been omitted.")
        return []

    fields = _parse_mbox_file_to_contacts_fields_list(
        mbox_file_path,
        omit_from_fields=omit_from_fields,
        omit_to_fields=omit_to_fields,
    )

    if dump_fields_to_json:
        mbox_path = Path(mbox_file_path)
        dump_json_path = mbox_path.parent / (mbox_path.stem + " - fields.json")

        _dump_to_json_file(fields, dump_json_path)
        logger.info(f"mbox fields written to '{dump_json_path.resolve()}'")

    return _mbox_fields_to_emails_with_names(fields, out_file_path)


######################### End of library, example of use below


def mbox_example():
    # Get "From" and "To" contacts from a .mbox file.
    emails_with_names = get_contact_emails_with_names_from_mbox(
        "All mail Including Spam and Trash.mbox",
    )


def mbox_and_dump_fields_to_json_example():
    # Get "From" and "To" contacts from a .mbox file and dump "From" and
    # "To" fields to a .json file.
    emails_with_names = get_contact_emails_with_names_from_mbox(
        "All mail Including Spam and Trash.mbox",
        dump_fields_to_json=True,
    )


def mbox_example2():
    # Get only "From" contacts from a .mbox file and dump "From" fields to a
    # .json file.
    emails_with_names = get_contact_emails_with_names_from_mbox(
        "All mail Including Spam and Trash.mbox",
        omit_to_fields=True,
    )


def mbox_example3():
    # Get only "To" contacts from a .mbox file and dump "To" fields to a
    # .json file.
    emails_with_names = get_contact_emails_with_names_from_mbox(
        "All mail Including Spam and Trash.mbox",
        omit_from_fields=True,
    )


def json_example():
    # Use a previously created fields .json file instead of
    # reparsing the .mbox file for efficiency
    emails_with_names = (
        get_contact_emails_with_names_from_json_with_mbox_fields(
            "All mail Including Spam and Trash - fields.json",
        )
    )
