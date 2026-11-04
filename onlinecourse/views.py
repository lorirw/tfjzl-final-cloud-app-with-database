
import logging

from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import generic
from django.views.decorators.http import require_POST

from .models import Course, Enrollment, Question, Choice, Submission


# Get an instance of a logger
logger = logging.getLogger(__name__)


# User registration
def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )

    elif request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('psw', '')
        first_name = request.POST.get('firstname', '')
        last_name = request.POST.get('lastname', '')

        if User.objects.filter(username=username).exists():
            context['message'] = "User already exists."
            return render(
                request,
                'onlinecourse/user_registration_bootstrap.html',
                context
            )

        user = User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            password=password
        )

        login(request, user)
        return redirect('onlinecourse:index')


# User login
def login_request(request):
    context = {}

    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('psw', '')

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "Invalid username or password."

    return render(
        request,
        'onlinecourse/user_login_bootstrap.html',
        context
    )


# User logout
def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


# Check whether a user is enrolled in a course
def check_if_enrolled(user, course):
    if not user.is_authenticated:
        return False

    return Enrollment.objects.filter(
        user=user,
        course=course
    ).exists()


# Display list of courses
class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user

        courses = list(
            Course.objects.order_by('-total_enrollment')[:10]
        )

        for course in courses:
            course.is_enrolled = check_if_enrolled(user, course)

        return courses


# Display course details
class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


# Enroll in a course
def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if not user.is_authenticated:
        return redirect('onlinecourse:login')

    if not check_if_enrolled(user, course):
        Enrollment.objects.create(
            user=user,
            course=course,
            mode='honor'
        )

        course.total_enrollment += 1
        course.save(update_fields=['total_enrollment'])

    return HttpResponseRedirect(
        reverse(
            'onlinecourse:course_details',
            args=(course.id,)
        )
    )


# Extract selected answers from the submitted exam
def extract_answers(request):
    submitted_answers = []

    for key, value in request.POST.items():
        if key.startswith('choice_'):
            try:
                choice_id = int(value)
                submitted_answers.append(choice_id)
            except (ValueError, TypeError):
                continue

    return submitted_answers


# Submit exam answers
@require_POST
def submit(request, course_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(
        Course,
        pk=course_id
    )

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    selected_ids = extract_answers(request)

    valid_choices = Choice.objects.filter(
        id__in=selected_ids,
        question__course=course
    )

    # Create an exam submission
    submission = Submission.objects.create(
        enrollment=enrollment
    )

    # Save selected choices
    submission.choices.set(valid_choices)

    # Redirect to exam results
    return redirect(
        'onlinecourse:exam_result',
        course_id=course.id,
        submission_id=submission.id
    )


# Calculate the exam score and display results
def show_exam_result(request, course_id, submission_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(
        Course,
        pk=course_id
    )

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
        enrollment__user=request.user
    )

    choices = submission.choices.all()

    total_score = 0
    questions = course.question_set.all()

    for question in questions:

        # Get correct answers for this question
        correct_choice_ids = set(
            question.choice_set.filter(
                is_correct=True
            ).values_list('id', flat=True)
        )

        # Get answers selected by the learner
        selected_choice_ids = set(
            choices.filter(
                question=question
            ).values_list('id', flat=True)
        )

        # Award points only when all selections are correct
        if correct_choice_ids == selected_choice_ids:
            total_score += question.grade

    context = {
        'course': course,
        'grade': total_score,
        'choices': choices,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )
