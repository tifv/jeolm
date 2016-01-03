_jeolm_completion() {

if [[ -z $JEOLM_PYTHON ]];
then
    local JEOLM_PYTHON
    JEOLM_PYTHON=python
fi

if [[ -z $JEOLM_PATH ]];
then
    local JEOLM_PATH
    JEOLM_PATH=$( $JEOLM_PYTHON \
        -c 'import jeolm; path, = jeolm.__path__; print(path)' )
fi

local current
current="${COMP_WORDS[COMP_CWORD]}"

local jeolm_root

local inspected_index
local inspected
inspected_index=1
while true;
do
    inspected="${COMP_WORDS[inspected_index]}"

    if [[ "$inspected" == -* ]];
    then
        if [[ $COMP_CWORD == $inspected_index ]];
        then
            case "$inspected" in
                -R)
                    COMPREPLY=( --root ) ;;
                -v)
                    COMPREPLY=( --verbose ) ;;
                -C)
                    COMPREPLY=( --no-colour ) ;;
                --*)
                    COMPREPLY=( $(compgen \
                      -W '--root --verbose --no-colour' -- $inspected) ) ;;
                *)
                    COMPREPLY=() ;;
            esac
            return 0
        elif [[ ( $inspected == --root ) || ( $inspected == -R ) ]];
        then
            if [[ $COMP_CWORD == $(( $inspected_index + 1 )) ]];
            then
                COMPREPLY=( $(compgen -o dirnames -A directory "$current") )
                return 0
            fi
            jeolm_root=${COMP_WORDS[inspected_index+1]}
            inspected_index=$(( $inspected_index + 2 ))
            continue
        fi
    else
        break
    fi
    inspected_index=$(( $inspected_index + 1 ))
done

if [[ $COMP_CWORD == $inspected_index ]];
then
    COMPREPLY=( $(compgen \
        -W 'build buildline review init list spell makefile excerpt clean' \
        -- $inspected) )
    return 0
fi

case $inspected in
    clean)
        return 0 ;;
    init)
        COMPREPLY=( $(compgen \
            -W "$( cat $JEOLM_PATH/resources/RESOURCES.yaml | grep '^.' | \
                grep -v '^ ' | grep -v '^#' | sed 's/:$//' )" \
            -- "$current" ) )
        return 0 ;;
    review)
        COMPREPLY=( $(compgen -o filenames -A file -- "$current") )
        return 0 ;;
    build|list|spell|makefile|excerpt)
        ;;
    *)
        return 1 ;;
esac

if [[ -z $jeolm_root ]];
then
    jeolm_root=$(readlink -f .)
    while [[ ! -d "$jeolm_root/.jeolm" ]];
    do
        jeolm_root=$(dirname $jeolm_root)
        if [[ $jeolm_root != /?* ]];
        then
            return 1
        fi
    done
else
    jeolm_root=$(readlink -f "$jeolm_root")
    if [[ ! -d "$jeolm_root/.jeolm" ]];
    then
        return 1
    fi
fi

# By that time, we must have found a $jeolm_root

local targets_cache=$jeolm_root/build/targets.cache.list
local metadata_cache=$jeolm_root/build/metadata.cache.pickle

if [[ "$targets_cache" -ot "$metadata_cache" ]];
then
    # Rebuild completion database
    ( cd "$jeolm_root";
        $JEOLM_PYTHON -m jeolm.scripts.print_target_list > "$targets_cache"
    ) || { rm -f "$targets_cache"; return 1; }
fi

if [[ "$current" == *" "* ]];
then
    return 0
fi

if [[ "$current" != /* ]];
then
    COMPREPLY=( /"$current" )
    return 0
fi

COMPREPLY=( $(grep -x "$current"'[^/]*/\?' "$targets_cache") )

}
