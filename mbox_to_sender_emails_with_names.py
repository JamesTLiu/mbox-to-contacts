import json
import mailbox
import re
from pathlib import Path
from collections import defaultdict
from typing import *

from gmail_mbox_parser import GmailMboxMessage


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


def _mbox_sender_fields_to_email_and_names_dict(
    mbox_sender_fields: Iterable[str],
) -> defaultdict[str, set]:
    """Convert mbox sender fields to a dict mapping emails to their set
    of sender names.

    Args:
        mbox_sender_fields (Iterable[str]): The sender fields of an
            mbox file.

    Raises:
        ValueError: No sender name + email found in sender field.

    Returns:
        defaultdict[str, set]: A dict mapping emails to their set of
            sender names.
    """
    email_to_sender_names = defaultdict(set)

    for sender in mbox_sender_fields:
        match = re.search(
            r"^(?P<sender_name>[^<>]*)<(?P<email>[^<>]*)>\s*$", sender
        )

        if not match:
            match = re.search(
                r"(?P<sender_name>^)(?P<email>[^<>]+@[^<>]+)$", sender
            )

        if not match:
            raise ValueError(
                f"No sender name + email found in sender field: {sender}"
            )

        email = match.group("email").strip()
        sender_name = match.group("sender_name").strip()

        if sender_name:
            email_to_sender_names[email].add(sender_name)
        else:
            email_to_sender_names[email]

    return email_to_sender_names


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


def _parse_mbox_file_to_sender_list(mbox_file_path: str) -> list[str]:
    """Return a list with the sender fields in the mbox file.

    Args:
        mbox_file_path (str): The path to the mbox file.

    Returns:
        list[str]: A list with the sender fields in the mbox file.
    """
    mb = mailbox.mbox(mbox_file_path)
    num_entries = len(mb)
    sender_list = []

    for email_obj in mb:
        email_data = GmailMboxMessage(email_obj)
        email_data.parse_email()
        sender_list.append(email_data.email_from)

    print(f"entries in '{mbox_file_path}': {num_entries}")
    return sender_list


def _mbox_sender_fields_to_sender_emails_with_sender_names(
    mbox_sender_fields: Iterable[str], out_file_path: str | Path | None = None
) -> list[tuple[str, tuple]]:
    """Convert mbox sender fields to a list of (email, sender_names)
    tuples. List is sorted by the @... portion of the email and then the
    email itself. Optionally, writes the result to a file if given.

    Args:
        mbox_sender_fields (Iterable[str]): The sender fields from mbox
            messages.
        json_file_path (str, Path, optional): The path to the file to
            write the result to in json if given. Defaults to None.

    Raises:
        ValueError: @ not found in an email.

    Returns:
        list[tuple[str, tuple]]: A list of (email, sender_names) tuples.
            sender_names is a tuple with all sender names for the email.
    """
    email_to_sender_names = _mbox_sender_fields_to_email_and_names_dict(
        mbox_sender_fields
    )
    hashable_email_to_sender_names = _dict_with_set_to_hashable(
        email_to_sender_names
    )

    def to_base_email_and_email(
        email_with_sender_names: tuple[str, Any]
    ) -> tuple[str, str]:
        """Return a tuple as (part after the @ in an email, email) given
        a tuple with (email, sender_names).

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
                    f"more than 1 @ in email section and unable to extract"
                    f" the 1st email: '{email}'"
                )

        domain = email.split("@")[1]

        if not domain:
            raise ValueError(f"Invalid email: no domain found (nothing after @): '{email}'")

        domain_parts = re.split(r"\W", domain)
        domain_parts.reverse()

        return (*domain_parts, email)

    sender_emails_with_sender_names = sorted(
        hashable_email_to_sender_names, key=to_base_email_and_email
    )

    if out_file_path:
        _dump_to_json_file(sender_emails_with_sender_names, out_file_path)
        print(
            "mbox 'From' email addresses with their sender names written to"
            f" '{Path(out_file_path).resolve()}"
        )

    return sender_emails_with_sender_names


def json_mbox_senders_to_sender_emails_with_sender_names(
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

    sender_fields = _load_json(json_file_path)

    return _mbox_sender_fields_to_sender_emails_with_sender_names(
        sender_fields, out_file_path
    )


def mbox_to_sender_emails_with_sender_names(
    mbox_file_path: str,
    out_file_path: str | Path | None = None,
    dump_sender_fields_to_json=False,
) -> list[tuple[str, tuple]]:
    """Return a list of (email, sender_names) tuples for the messages in
    the mbox file. sender_names is a tuple with all sender names for the
    email.

    Args:
        mbox_file_path (str): The path to the mbox file.
        out_file_path (str, Path, optional): The path to the file to
            write the result to in json if given. Defaults to "".
        dump_sender_fields_json (bool, optional): If True, the sender
            fields from the mbox file will be output to a json file.
            Defaults to None.

    Returns:
        list[tuple[str, tuple]]: A list of (email, sender_names) tuples.
            sender_names is a tuple with all sender names for the email.
    """
    if out_file_path:
        _ensure_is_file(out_file_path)

    _ensure_existing_mbox_file(mbox_file_path)

    sender_fields = _parse_mbox_file_to_sender_list(mbox_file_path)

    if dump_sender_fields_to_json:
        mbox_path = Path(mbox_file_path)
        dump_json_path = mbox_path.parent / (
            mbox_path.stem + " - sender fields.json"
        )

        _dump_to_json_file(sender_fields, dump_json_path)
        print(f"mbox sender fields written to '{dump_json_path.resolve()}'")

    return _mbox_sender_fields_to_sender_emails_with_sender_names(
        sender_fields, out_file_path
    )


######################### End of library, example of use below


def mbox_example():
    # Use a .mbox file.
    sender_emails_with_sender_names = mbox_to_sender_emails_with_sender_names(
        "All mail Including Spam and Trash.mbox",
        "sender_emails_with_sender_names.json",
        True,
    )


def json_example():
    # Use a previously created sender fields .json file instead of
    # reparsing the .mbox file for efficiency
    sender_emails_with_sender_names = (
        json_mbox_senders_to_sender_emails_with_sender_names(
            "All mail Including Spam and Trash - sender fields.json",
            "sender_emails_with_sender_names.json",
        )
    )
