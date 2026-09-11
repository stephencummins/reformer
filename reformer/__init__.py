"""reformer — find the forms a Microsoft 365 tenant move will break.

Four unrelated technologies get called "a form", and each breaks differently
when a tenant changes. None of them break loudly: the solution imports, the
report says green, and the screen a person types into is gone or points at
nothing. reformer inventories what exists, says what each one needs, and gives
the effort behind the answer.

It reads. It never writes to a tenant and never changes a package.
"""

__version__ = "0.1.0"
