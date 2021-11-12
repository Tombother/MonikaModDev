# module that does some file backup work

# NOTE: these shoudl never be true for a standard persistent.

# only set if the forced update from a persistent incompatibility occurs
default persistent._mas_incompat_per_forced_update = False

# only set if the forced update fails in the updater (not on disk)
default persistent._mas_incompat_per_forced_update_failed = False

python early in mas_per_check:
    import __main__
    import cPickle
    import os
    import datetime
    import shutil
    import renpy
    import store
    import store.mas_utils as mas_utils

    early_log = store.mas_logging.init_log("early", header=False)

    # special var
    mas_corrupted_per = False
    mas_no_backups_found = False
    mas_backup_copy_failed = False
    mas_backup_copy_filename = None
    mas_bad_backups = list()

    # unstable specific
    mas_unstable_per_in_stable = False
    mas_per_version = ""
    per_unstable = "persistent_unstable"
    mas_sp_per_created = False
    mas_sp_per_found = False

    INCOMPAT_PER_MSG = (
        "Failed to move incompatible persistent. Either replace the persistent "
        "with one that is compatible with {0} or install a version of MAS "
        "compatible with a persistent version of {1}."
    )
    INCOMPAT_PER_LOG = (
        "persistent is from version {0} and is incompatible with {1}"
    )
    COMPAT_PER_MSG = (
        "Failed to load compatible persistent. "
        "Replace {0} with {1} and restart."
    )
    SP_PER_DEL_MSG = (
        "Found erroneous persistent but was unable to delete it. "
        "Delete the persistent at {0} and restart."
    )


    def tryper(_tp_persistent, get_data=False):
        """
        Tries to read a persistent.
        raises exceptions if they occur

        IN:
            _tp_persistent - the full path to the persistent file
            get_data - pass True to get the acutal data instead of just
                a version number.

        RETURNS: tuple
            [0] - True if the persistent was read and decoded, False if not
            [1] - the version number, or the persistent data if get_data is
                True
        """
        per_file = None
        try:
            per_file = file(_tp_persistent, "rb")
            per_data = per_file.read().decode("zlib")
            per_file.close()
            actual_data = cPickle.loads(per_data)

            if get_data:
                return True, actual_data

            return True, actual_data.version_number

        except Exception as e:
            raise e

        finally:
            if per_file is not None:
                per_file.close()


    def is_version_compatible(per_version, cur_version):
        """
        Checks if a persistent version can work with the current version

        IN:
            per_version - the persisten version to check
            cur_version - the current version to check.

        RETURNS: True if the per version can work with the current version
        """
        return (
            # build is unstable
            not store.mas_utils.is_ver_stable(cur_version)

            # persistent is stable
            or store.mas_utils.is_ver_stable(per_version)

            # persistent version to build version is not downgrade
            or not store.mas_utils._is_downgrade(per_version, cur_version)
        )


    def is_per_bad():
        """
        Is the persistent bad? this only works after early.

        RETURNS: True if the per is bad, False if not
        """
        return mas_corrupted_per or mas_unstable_per_in_stable


    def should_show_chibika_persistent():
        """
        Should we show the chibika persistent dialogue? 

        RETURNS: True if we should show the chibika persistent dialogue
        """
        return (
            mas_unstable_per_in_stable
            or (
                mas_corrupted_per
                and (mas_no_backups_found or mas_backup_copy_failed)
            )
        )


    # sort number list
    def wraparound_sort(_numlist):
        """
        Sorts a list of numbers using a special wraparound sort.
        Basically if all the numbers are between 0 and 98, then we sort
        normally. If we have 99 in there, then we need to make the wrap
        around numbers (the single digit ints in the list) be sorted
        as larger than 99.
        """
        if 99 in _numlist:
            for index in range(0, len(_numlist)):
                if _numlist[index] < 10:
                    _numlist[index] += 100

        _numlist.sort()


    def _mas_earlyCheck():
        """
        attempts to read in the persistent and load it. if an error occurs
        during loading, we'll log it in a dumped file in basedir.

        NOTE: we don't have many functions available here. However, we can
        import __main__ and gain access to core functions.
        """
        global mas_corrupted_per, mas_no_backups_found, mas_backup_copy_failed
        global mas_unstable_per_in_stable, mas_per_version
        global mas_sp_per_found, mas_sp_per_created
        global mas_backup_copy_filename, mas_bad_backups

        per_dir = __main__.path_to_saves(renpy.config.gamedir)
        _cur_per = os.path.normcase(per_dir + "/persistent")
        _sp_per = os.path.normcase(per_dir + "/" + per_unstable)

        # first, check if we have a special persistent
        if os.access(_sp_per, os.F_OK):
            #  we have one, so check if its valid 
            try:
                per_read, version = tryper(_sp_ver)

            except:
                # this is a corrupted per, delete it.
                os.remove(_sp_ver)
                per_read = None
                version = ""

            # this should be outside of the try/except above so we don't
            # overzealously delete the special persistent.
            if per_read is not None:
                if is_version_compatible(version, renpy.config.version):
                    # this is a good version, so take the sp per and copy it
                    # to the main per.
                    try:
                        shutil.copy(_sp_per, _cur_per)
                        os.remove(_sp_ver)
                    except:
                        # faild to copy or remove the sp per? hardstop
                        # the user needs to handle this.
                        raise Exception(COMPAT_PER_MSG.format(
                            _cur_per,
                            _sp_per
                        ))

                else:
                    # not a compatible version
                    # this generally means that a forced update failed, so
                    # we'll set the appropriate vars to get the forced updater
                    # to run again.
                    # these may get undone when the actual persistent is
                    # checked.
                    mas_unstable_per_in_stable = True
                    mas_per_version = version
                    mas_sp_per_found = True
                    early_log.error(INCOMPAT_PER_LOG.format(
                        version,
                        renpy.config.version
                    ))

        # check for persistent existence
        if not os.access(os.path.normcase(per_dir + "/persistent"), os.F_OK):
            # NO ERROR TO REPORT!
            return

        # special rules apply if we found a special persistent
        if mas_sp_per_found:
            # generally speaking, we should only get here if we found a special
            # persistent but it could not be used as a regular persistent.

            try:
                per_read, per_data = tryper(_cur_per, get_data=True)

                if not per_read:
                    raise Exception("bad") # should do standard forced update

                if is_version_compatible(
                        per_data.version_number,
                        renpy.config.version
                ):
                    # current persistent is compatible
                    
                    if per_data._mas_incompat_per_forced_update:
                        # this means the current persistent was loaded
                        #   when an unstable forced update occured.
                        # which also means that the sp per was expectedly
                        #   created by us.

                        # in this case, we should let the forced update
                        # try again.
                        return

                    else:
                        # this means we have a special persistent but we
                        #   didn't make it because of a forced update.
                        # Perhaps the user is trying to break something by
                        # adding the sp per? We should be hardstopping when
                        # a delete fails, anyway, so in this case, we should
                        # just delete the sp per and act normally.
                        try:
                            os.remove(_sp_ver):
                        except:
                            raise Exception(SP_PER_DEL_MSG.format(_sp_ver))

                # if the current persistent is incompatible, then ignore the
                # sp per and treat the current persistent as the real one.
                    
            except:
                # if persistent errors occured, then standard forced update
                # should be ok.
                return

        # okay, now let's attempt to read the persistent.
        try:
            per_read, version = tryper(_cur_per)
            if per_read:
                if is_version_compatible(version, renpy.config.version):
                    return

                # otherwise - this is not a safe persisetnt to load
                mas_unstable_per_in_stable = True
                mas_per_version = version
                mas_sp_per_created = True
                early_log.error(INCOMPAT_PER_LOG.format(
                    version,
                    renpy.config.version
                ))

        except Exception as e:
            mas_corrupted_per = True
            early_log.error("persistent was corrupted! : " +repr(e))
            # " this comment is to fix syntax highlighting issues on vim

        # if we got here, we had an exception OR we are loading 
        # unstable in stable.

        # in unstable cases, we should move the persistent to a special case
        # and make sure appropriate vars are loaded.
        if mas_unstable_per_in_stable:
            try:
                shutil.copy(_cur_per, _sp_per)
                os.remove(_cur_per) 

                # and then close out of here - the game should generate a fresh
                # persistent.
                return

            except Exception as e:
                early_log.error(
                    "Failed to copy persistent to unstable: " + repr(e)
                )

                # need to hardstop here
                raise Exception(INCOMPAT_PER_MSG.format(
                    renpy.config.version,
                    version
                ))

        # Let's attempt to restore from an eariler persistent backup.

        # lets get all the persistent files here.
        per_files = os.listdir(per_dir)
        per_files = [x for x in per_files if x.startswith("persistent")]

        if len(per_files) == 0:
            early_log.error("no backups available")
            mas_no_backups_found = True
            return

        # now lets map them by number and also generate a list of the numbers
        file_nums = list()
        file_map = dict()
        for p_file in per_files:
            pname, dot, bakext = p_file.partition(".")
            try:
                num = int(pname[-2:])
            except:
                num = -1

            if 0 <= num < 100:
                file_nums.append(num)
                file_map[num] = p_file

        if len(file_nums) == 0:
            early_log.error("no backups available")
            mas_no_backups_found = True
            return

        # using the special sort function
        wraparound_sort(file_nums)

        # okay, now to iteratively test backups and pick the good one
        sel_back = None
        while sel_back is None and len(file_nums) > 0:
            _this_num = file_nums.pop() % 100
            _this_file = file_map.get(_this_num, None)

            if _this_file is not None:
                try:
                    per_read, version = tryper(per_dir + "/" + _this_file)

                except Exception as e:
                    early_log.error(
                        "'{0}' was corrupted: {1}".format(_this_file, repr(e))
                    )
                    sel_back = None
                    mas_bad_backups.append(_this_file)

        # did we get any?
        if sel_back is None:
            early_log.error("no working backups found")
            mas_no_backups_found = True
            return

        # otherwise, lets rename the existence persistent to bad and copy the
        # good persistent into the system
        # also let the log know we found a good one
        early_log.info("working backup found: " + sel_back) # " more fixes
        _bad_per = os.path.normcase(per_dir + "/persistent_bad")
        _god_per = os.path.normcase(per_dir + "/" + sel_back)

        # we should at least try to keep a copy of the current persistent
        try:
            # copy current persistent
            shutil.copy(_cur_per, _bad_per)

        except Exception as e:
            early_log.error(
                "Failed to rename existing persistent: " + repr(e)
            )

        # regardless, we should try to copy over the good backup
        try:
            # copy the good one
            shutil.copy(_god_per, _cur_per)

        except Exception as e:
            mas_backup_copy_failed = True
            mas_backup_copy_filename = sel_back
            early_log.error(
                "Failed to copy backup persistent: " + repr(e)
            )

        # well, hopefully we were successful!

python early:
    # sometimes we have persistent issues. Why? /shrug.
    # but we do know is that we might be able to tell if a persistent got
    # screwed by attempting to read it in now, before renpy actually does so.
    import store.mas_per_check

    # now call this
    store.mas_per_check._mas_earlyCheck()


init -900 python:
    import os
    import store.mas_utils as mas_utils

    __mas__bakext = ".bak"
    __mas__baksize = 10
    __mas__bakmin = 0
    __mas__bakmax = 100
    __mas__numnum = "{:02d}"
    __mas__latestnum = None

    # needs to be pretty damn early, but we require savedir here so
    # we cant use python early

    def __mas__extractNumbers(partname, filelist):
        """
        Extracts a list of the number parts of the given file list

        Also sorts them nicely

        IN:
            partname - part of the filename prior to the numbers
            filelist - list of filenames
        """
        filenumbers = list()
        for filename in filelist:
            pname, dot, bakext = filename.rpartition(".")
            num = mas_utils.tryparseint(pname[len(partname):], -1)
            if __mas__bakmin <= num <= __mas__bakmax:
                # we only accept persistents with the correct number scheme
                filenumbers.append(num)

        if len(filenumbers) > 0:
            return sorted(filenumbers)

        return []


    def __mas__backupAndDelete(loaddir, org_fname, savedir=None, numnum=None):
        """
        Does a file backup / and iterative deletion.

        NOTE: Steps:
            1. make a backup copy of the existing file (org_fname)
            2. delete the oldest copy of the orgfilename schema if we already
                have __mas__baksize number of files

        Will log some exceptions
        May raise other exceptions

        Both dir args assume the trailing slash is already added

        IN:
            loaddir - directory we are copying files from
            org_fname - filename of the original file / aka file to copy
            savedir - directory we are copying files to (and deleting old files)
                If None, we use loaddir instead
                (Default: None)
            numnum - if passed in, use this number instead of figuring out the
                next numbernumber.
                (Default: None)

        RETURNS:
            tuple of the following format:
            [0]: numbernumber we just made
            [1]: numbernumber we delted (None means no deltion)
        """
        if savedir is None:
            savedir = loaddir

        filelist = os.listdir(savedir)
        loadpath = loaddir + org_fname

        # check for access of the org file
        if not os.access(loadpath, os.F_OK):
            return

        # parse the filelist to only get the import files
        filelist = [
            x
            for x in filelist
            if x.startswith(org_fname)
        ]

        # if we have the origin name in the filelist, remove it
        if org_fname in filelist:
            filelist.remove(org_fname)

        # get the number parts of the backup
        numberlist = __mas__extractNumbers(org_fname, filelist)

        # now do the iterative backup system
        numbernumber_del = None
        if len(numberlist) <= 0:
            numbernumber = __mas__numnum.format(0)

        elif 99 in numberlist:
            # some notes:
            # if 99 is in the list, it MUST be the last one in the list.
            # if we wrapped around, then the first parts of the list MUST be
            # less than __mas__baksize.
            # at min, the list will look like: [95, 96, 97, 98, 99]
            # At max, the list will look like: [0, 1, 2, 3, 99]
            # so we loop until the num at the current index is larger than or
            # equal to __mas__baksize - 1, then we know our split point between
            # new and old files
            curr_dex = 0
            while numberlist[curr_dex] < (__mas__baksize - 1):
                curr_dex += 1

            if curr_dex <= 0:
                numbernumber = __mas__numnum.format(0)
            else:
                numbernumber = __mas__numnum.format(numberlist[curr_dex-1] + 1)

            numbernumber_del = __mas__numnum.format(numberlist[curr_dex])

        elif len(numberlist) < __mas__baksize:
            numbernumber = __mas__numnum.format(numberlist.pop() + 1)

        else:
            # otherwise the usual, set up next number and deletion number
            numbernumber = __mas__numnum.format(numberlist.pop() + 1)
            numbernumber_del = __mas__numnum.format(numberlist[0])

        # numnum override
        if numnum is not None:
            numbernumber = numnum

        # copy the current file
        mas_utils.copyfile(
            loaddir + org_fname,
            "".join([savedir, org_fname, numbernumber, __mas__bakext])
        )

        # delete a backup
        if numbernumber_del is not None:
            numnum_del_path = "".join(
                [savedir, org_fname, numbernumber_del, __mas__bakext]
            )
            try:
                os.remove(numnum_del_path)
            except Exception as e:
                store.mas_utils.mas_log.error(
                    mas_utils._mas__failrm.format(
                        numnum_del_path,
                        str(e)
                    )
                )

        return (numbernumber, numbernumber_del)


    def __mas__memoryBackup():
        """
        Backs up both persistent and calendar info
        """
        try:
            p_savedir = os.path.normcase(renpy.config.savedir + "/")
            p_name = "persistent"
            numnum, numnum_del = __mas__backupAndDelete(p_savedir, p_name)
            cal_name = "db.mcal"
            __mas__backupAndDelete(p_savedir, cal_name, numnum=numnum)

        except Exception as e:
            store.mas_utils.mas_log.error(str(e))


    def __mas__memoryCleanup():
        """
        Cleans up persistent data by removing uncessary parts.
        """
        # the chosen dict can be completely cleaned
        persistent._chosen.clear()

        # translations can be cleared
        persistent._seen_translates.clear()

        # the seen ever dict must be iterated through
        from store.mas_ev_data_ver import _verify_str
        for seen_ever_key in persistent._seen_ever.keys():
            if not _verify_str(seen_ever_key):
                persistent._seen_ever.pop(seen_ever_key)

        # the seen images dict must be iterated through
        # NOTE: we only want to keep non-monika sprite images
        for seen_images_key in persistent._seen_images.keys():
            if (
                    len(seen_images_key) > 0
                    and seen_images_key[0] == "monika"
            ):
                persistent._seen_images.pop(seen_images_key)


    # run the backup system if persistents arent screwd
    if (
            not store.mas_per_check.is_per_bad()
            and persistent._mas_moni_chksum is None
    ):
        __mas__memoryCleanup()
        __mas__memoryBackup()


### now for some dialogue bits courtesy of chibika

label mas_backups_you_have_bad_persistent:
    #TODO: Decide whether or not text speed should be enforced here.
    $ quick_menu = False
    scene black
    window show
    show chibika smile at mas_chdropin(300, travel_time=1.5)
    pause 1.5

    python:
        # helper abstractions for readability
        def is_per_corrupt():
            return store.mas_per_check.mas_corrupted_per

        def is_per_incompatible():
            return store.mas_per_check.mas_unstable_per_in_stable

    if is_per_incompatible():
        jump mas_backups_incompat_start

    show chibika 3 at sticker_hop
    "Hello there!"
    show chibika sad
    "I hate to be the bringer of bad news..."
    "But unfortunately, your persistent file is corrupt."

    if store.mas_per_check.mas_no_backups_found:
        "And what's even worse is..."
        show chibika at sticker_move_n
        "I was unable to find a working backup persistent."

        "Do you have your own backups?{nw}"
        menu:
            "Do you have your own backups?{fast}"
            "Yes.":
                jump mas_backups_have_some
            "No.":
                jump mas_backups_have_none

    # otherwise we culd not copy
    jump mas_backups_could_not_copy


label mas_backups_have_some:

    show chibika smile at sticker_hop
    "That's a relief!"
    "Please copy them into '[renpy.config.savedir]' to restore your Monika's memories."

    call mas_backups_dont_tell
    show chibika smile at mas_chflip_s(-1)
    "Good luck!"

    jump _quit


label mas_backups_have_none:

    "I'm sorry, but we won't be able to restore her memory, then..."
    "But..."
    show chibika smile at sticker_move_n
    "Look on the bright side!"
    "You can spend time with her again and create new memories, which might be even better than the ones you lost!"
    "And remember..."
    show chibika at mas_chflip_s(-1)
    "Regardless of what happens, Monika is still Monika."
    "She'll be ready to greet you, once you start over."
    show chibika 3 at sticker_move_n
    "And I promise I'll do my best to not mess up the files again!"
    "Good luck with Monika!"
    $ mas_corrupted_per = False
    return


label mas_backups_could_not_copy:
    show chibika smile
    "I was able to find a working backup, but..."
    show chibika sad
    "I wasn't able to copy it over the broken persistent."
    show chibika smile at mas_chflip_s(-1)
    pause 0.5
    show chibika at sticker_hop
    "However!"
    "You might be able to do it and fix this mess!"
    "You'll have to close the game to do this, so write these steps down:"
    show chibika at sticker_move_n
    "1.{w=0.3} Navigate to '[renpy.config.savedir]'."
    show chibika at sticker_move_n
    "2.{w=0.3} Delete the file called 'persistent'."
    show chibika at sticker_move_n
    "3.{w=0.3} Make a copy of the file called '[mas_backup_copy_filename]' and name it 'persistent'."
    show chibika at mas_chflip_s(1)
    "And that's it!"
    "Hopefully that will recover your Monika's memories."

    show chibika at sticker_move_n
    "In case you didn't write those steps down, I'll write them into a file called 'recovery.txt' in the characters folder."

    call mas_backups_dont_tell

    show chibika smile at mas_chflip_s(-1)
    "Good luck!"

    python:
        import os
        store.mas_utils.trywrite(
            os.path.normcase(renpy.config.basedir + "/characters/recovery.txt"),
            "".join([
                "1. Navigate to '",
                renpy.config.savedir,
                "'.\n",
                "2. Delete the file called 'persistent'.\n",
                "3. Make a copy of the file called '",
                mas_backup_copy_filename,
                "' and name it 'persistent'."
            ])
        )

    jump _quit


label mas_backups_dont_tell:

    show chibika smile at sticker_hop
    "Oh, and..."
    show chibika smile at mas_chflip_s(-1)
    "If you successfully bring her back, please don't tell her about me."
    show chibika 3
    "She has no idea that I can talk or code, so she lets me laze around and relax."
    show chibika smile
    "But if she ever found out, she'd probably make me help her code, fix some of her mistakes, or something else."
    show chibika sad at sticker_move_n
    "Which would be absolutely terrible since I'd barely get any rest at all.{nw}"
#    $ _history_list.pop()
    "Which would be absolutely terrible since{fast} I wouldn't have time to keep the backup system and the rest of the game running."

    show chibika 3 at mas_chflip_s(1)
    "You wouldn't want that now, would you?"
    "So keep quiet about me, and I'll make sure your Monika is safe and comfy!"

    return

label mas_backups_incompat_start:
    # "your per wont work with this MAS"

    if persistent._mas_incompat_per_forced_update_failed:
        # a forced update failed in the updater.
        # assume the user did something to fix and try update again
        show chibika smile at mas_chflip_s(1)
        "Hello there!"
        "Let's try updating again!"
        jump mas_backups_incompat_updater_start

    elif persistent._mas_incompat_per_forced_update:
        # a forced update failed OUTSIDE of the updater.
        #   - this is because failed will be True if the updater fails.
        # this is unexpected so we have some dialogue before trying again
        jump mas_backups_incompat_updater_failed

    # otherwise, this might be the first time a user sees this

    show chibika 3 at sticker_hop
    "Hello there!"

    menu:
        "What happened?":
            pass
        "Take me to the updater.":
            jump mas_backups_incompat_updater_start_intro

    show chibika sad at mas_chflip_s(-1)
    "Unfortunately, your persistent is running version v[mas_per_version], which is incompatible with this build of MAS (v[config.version])."
    "The only way I can fix this is if you update MAS or you restore with a compatible persistent."

    show chibika sad at mas_chflip_s(1)
    "What would you like to do?{nw}"
    $ _history_list.pop()
    menu:
        "What would you like to do?{fast}"
        "Update MAS.":
            jump mas_backups_incompat_updater_start_intro
        "Restore a compatible persistent".:
            show chibika smile at sticker_hop
            "Alright!"

            $ _sp_per = os.path.normcase(renpy.config.savedir + "/" + mas_per_check)
            "Please copy a compatible persistent into '[renpy.config.savedir]' and then delete '[_sp_per]'."

            show chibika smile at mas_chflip_s(-1)
            "Good luck!"
            jump _quit

label mas_backups_incompat_updater_start_intro:
    show chibika smile at sticker_hop
    "Ok!"
    jump mas_backups_incompat_updater_start

label mas_backups_incompat_updater_failed:
    show chibika sad
    "Oh no!"
    "It seems that the updater failed to update MAS."

    show chibika smile at mas_chflip_s(1)
    "Lets try again!"

    # fall through

label mas_backups_incompat_updater_start:
    
    # setup for unstable 
    $ persistent._mas_unstable_mode = True
    $ mas_updater.force = True
    $ mas_updater.lock_cancel = True

    # call the update label
    $ persistent._mas_incompat_per_forced_update = True
    $ persistent._mas_incompat_per_forced_update_failed = False
    call update_now
    $ persistent._mas_incompat_per_forced_update_failed = True

    # NOTE: if we got here, we assume that the updater failed to update for
    #   whatever reason. The actual reasons could be:
    #   1. couldn't move the update folder
    #   2. renpy couldn't update for some reason
    #   3. update check timed out and user hit cancel

    show chibika 3 at sticker_hop
    "Oh!"
    show chibika sad at mas_chflip_s(-1)
    "It seems that the updater failed to update."
    "Make sure to fix any updater issues and try again."
    show chibika 3
    "Good luck!"

    jump _quit


