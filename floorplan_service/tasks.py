from celery import shared_task


@shared_task
def my_task(param):
    # Do something
    print(param)
