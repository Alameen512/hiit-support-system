from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Issue, Profile
from .services import eligible_staff

User = get_user_model()


class RegisterForm(UserCreationForm):
    """Public sign-up. It can only create students: there is no role field here."""
    first_name = forms.CharField(max_length=50, label="First name")
    last_name = forms.CharField(max_length=50, label="Last name")
    email = forms.EmailField(max_length=120)
    matric_number = forms.CharField(max_length=30, required=False, label="Student / matric number (optional)")
    phone = forms.CharField(max_length=20, required=False, label="Phone (optional)")

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.is_staff = False
        user.is_superuser = False
        user.save()
        profile = user.profile  # created by signal, role=student
        profile.matric_number = self.cleaned_data["matric_number"]
        profile.phone = self.cleaned_data["phone"]
        profile.save()
        return user


class IssueForm(forms.ModelForm):
    class Meta:
        model = Issue
        fields = ["title", "category", "priority", "description", "location"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Computer not working in IT Lab 2"}),
            "description": forms.Textarea(attrs={"rows": 6, "maxlength": 3000,
                                                 "placeholder": "Tell us what happened and what you have tried."}),
            "location": forms.TextInput(attrs={"placeholder": "e.g. IT Lab 2, Admin Office (optional)"}),
        }

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if len(title) < 5:
            raise forms.ValidationError("Please use a title of at least 5 characters.")
        return title

    def clean_description(self):
        text = self.cleaned_data["description"].strip()
        if len(text) < 15:
            raise forms.ValidationError("Please describe the problem in at least 15 characters.")
        return text


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=50)
    last_name = forms.CharField(max_length=50)
    email = forms.EmailField(max_length=120)

    class Meta:
        model = Profile
        fields = ["phone", "matric_number"]  # role is deliberately NOT editable

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["first_name"].initial = user.first_name
        self.fields["last_name"].initial = user.last_name
        self.fields["email"].initial = user.email
        self.order_fields(["first_name", "last_name", "email", "phone", "matric_number"])

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("Another account already uses this email.")
        return email

    def save(self, commit=True):
        for f in ("first_name", "last_name", "email"):
            setattr(self.user, f, self.cleaned_data[f])
        self.user.save(update_fields=["first_name", "last_name", "email"])
        return super().save(commit)


class AssignForm(forms.Form):
    assignee = forms.ModelChoiceField(queryset=User.objects.none(), required=False, empty_label="Unassigned")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignee"].queryset = eligible_staff()
        self.fields["assignee"].label_from_instance = lambda u: u.get_full_name() or u.get_username()


class StatusForm(forms.Form):
    status = forms.ChoiceField(choices=Issue.Status.choices)


class PriorityForm(forms.Form):
    priority = forms.ChoiceField(choices=Issue.Priority.choices)


class ResponseForm(forms.Form):
    message = forms.CharField(min_length=2, max_length=2000, widget=forms.Textarea(
        attrs={"rows": 4, "placeholder": "Write a response to the student..."}))
